# Gorani SketchUp 실기 시험 — SketchUp.exe -RubyStartup 이 파일. autotest.json의 대상지를 차례로 만들고 화면을 캡처한다.
# 패널(HtmlDialog)을 열고 사이드카 주소가 나오면 POST /cmd {cmd: generate}를 보낸다 — 호스트 호출은 패널이 받아 Ruby로 넘긴다(실사용과 같은 길).
# 끝 표시: 결과 폴더에 이번 시작 뒤 생긴 context.skp. 결과는 out 폴더의 PNG·log.txt·done.txt.
require "json"
require "net/http"
require "fileutils"

module GoraniAutotest
  CONFIG = File.join(File.dirname(__FILE__), "autotest.json")
  M = 39.3700787   # m → 인치

  def self.log(text)
    File.open(File.join(@out, "log.txt"), "a") { |f| f.puts("#{Time.now.strftime('%H:%M:%S')} #{text}") }
  end

  def self.start
    @cfg = JSON.parse(File.read(CONFIG))
    @out = @cfg["out"]
    FileUtils.mkdir_p(@out)
    File.delete(File.join(@out, "done.txt")) if File.exist?(File.join(@out, "done.txt"))
    log("start SketchUp #{Sketchup.version}, extension loaded: #{defined?(BSH::Gorani) ? 'yes' : 'no'}")
    unless defined?(BSH::Gorani)
      finish("extension not loaded")
      return
    end
    @index, @state, @since = 0, :panel, Time.now
    BSH::Gorani.show_panel
    @timer = UI.start_timer(2.0, true) { tick }
  rescue StandardError => e
    log("error #{e.class}: #{e.message}")
  end

  def self.url
    BSH::Gorani.instance_variable_get(:@url).to_s
  end

  def self.tick
    site = @cfg["sites"][@index]
    case @state
    when :panel
      if url.start_with?("http://127.0.0.1:")
        @ready_at ||= Time.now
        if Time.now - @ready_at > 12   # 패널 페이지가 다 열리고 이벤트 줄을 붙일 시간
          send_generate(site)
        end
      elsif Time.now - @since > 180
        finish("sidecar did not start")
      end
    when :running
      skp = Dir.glob(File.join(Dir.home, "Gorani", "result", "*", "context.skp")).find { |p| File.mtime(p) > @sent_at }
      if skp
        log("#{site['name']} done #{(Time.now - @sent_at).round}s #{skp}")
        UI.stop_timer(@timer)
        UI.start_timer(3.0, false) { capture(site); next_site }
        @state = :capturing
      elsif Time.now - @sent_at > (@cfg["timeout"] || 900)
        log("#{site['name']} timeout")
        next_site
      end
    end
  rescue StandardError => e
    log("tick error #{e.class}: #{e.message} #{e.backtrace.first}")
  end

  def self.send_generate(site)
    uri = URI(url.sub("/?token=", "/cmd?token="))
    body = JSON.generate(cmd: "generate", target: site["target"], options: site["options"])
    Net::HTTP.start(uri.host, uri.port, open_timeout: 5, read_timeout: 10) { |h| h.post(uri.request_uri, body, "Content-Type" => "application/json") }
    @sent_at, @state = Time.now, :running
    log("#{site['name']} generate sent")
  end

  def self.capture(site)
    model = Sketchup.active_model
    wrappers = model.entities.grep(Sketchup::Group).select { |g| g.get_attribute("Gorani", "GORANI_LOT_KEY") }
    wrapper = wrappers.max_by { |g| g.entities.length > 0 ? g.persistent_id : 0 }
    bounds = Geom::BoundingBox.new
    wrapper.entities.grep(Sketchup::Group).each do |g|
      next unless (site["focus"] || %w[CTX::Roads CTX::Rail::ballast]).include?(g.get_attribute("Gorani", "GORANI_LAYER"))
      bb = g.bounds
      bounds.add(bb.min.transform(wrapper.transformation), bb.max.transform(wrapper.transformation))
    end
    bounds = wrapper.bounds if bounds.empty?
    c = bounds.center
    target = Geom::Point3d.new(c.x, c.y, bounds.min.z + 1 * M)
    (site["views"] || []).each do |v|
      dx, dy, dz = v["offset"].map { |n| n * M }
      eye = Geom::Point3d.new(target.x + dx, target.y + dy, target.z + dz)
      model.active_view.camera = Sketchup::Camera.new(eye, target, Z_AXIS, true, 50)
      model.active_view.refresh
      path = File.join(@out, "#{site['name']}_#{v['name']}.png")
      model.active_view.write_image(filename: path, width: 1600, height: 1000, antialias: true)
      log("#{site['name']} image #{v['name']}")
    end
    stats = wrapper.entities.grep(Sketchup::Group).map { |g| [g.get_attribute("Gorani", "GORANI_LAYER"), g.entities.length] }
    log("#{site['name']} groups #{JSON.generate(stats)}")
    (site["edge_report"] || []).each do |layer|   # 그 레이어 그룹의 변 — 보이는 선(부드럽지 않음·숨김 아님)이 어디서 나오는지
      wrapper.entities.grep(Sketchup::Group).select { |g| g.get_attribute("Gorani", "GORANI_LAYER") == layer }.each do |g|
        edges = g.entities.grep(Sketchup::Edge)
        visible = edges.reject { |e| e.soft? || e.hidden? || e.smooth? }
        border = visible.select { |e| e.faces.length == 1 }
        inner = visible.select { |e| e.faces.length == 2 }
        angles = inner.map { |e| e.faces[0].normal.angle_between(e.faces[1].normal).radians.round(2) }.sort
        log("#{site['name']} edges #{layer}: faces #{g.entities.grep(Sketchup::Face).length} edges #{edges.length} soft #{edges.count(&:soft?)} " \
            "visible #{visible.length} (border #{border.length}, inner #{inner.length}, other #{visible.length - border.length - inner.length}) " \
            "inner angle deg min #{angles.first} median #{angles[angles.length / 2]} max #{angles.last}")
      end
    end
  rescue StandardError => e
    log("capture error #{e.class}: #{e.message} #{e.backtrace.first}")
  end

  def self.next_site
    @index += 1
    if @index >= @cfg["sites"].length
      finish("ok")
    else
      @state, @ready_at = :panel, nil
      @timer = UI.start_timer(2.0, true) { tick }
    end
  end

  def self.finish(status)
    UI.stop_timer(@timer) if @timer
    log("finish #{status}")
    File.write(File.join(@out, "done.txt"), status)
  end
end

UI.start_timer(5.0, false) { GoraniAutotest.start }
