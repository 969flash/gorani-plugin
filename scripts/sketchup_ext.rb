# Gorani SketchUp판 본문 — 확장 패키지에서는 bsh_gorani/main.rb(dev_deploy.py sketchup이 복사한다).
#
# SketchUp에는 파이썬이 없어 확장에 든 번들 파이썬(python/<플랫폼>/)으로 사이드카 scripts/cmd_sketchup.py를 띄운다.
# 사이드카가 첫 줄로 준 127.0.0.1 패널 주소를 UI::HtmlDialog가 연다 — 엔진·패널·데이터 받기는 전부 파이썬이고,
# 여기는 SketchUp 모델을 만지는 호스트 호출(host_call → rpc_<method>)만 한다. 응답은 패널 JS의 send({cmd: "host_reply"}).
# 모양: 대상지마다 최상위 그룹 하나(속성 GORANI_LOT_KEY) 안에 태그('CTX::Buildings')마다 그룹, 건물은 동마다 그룹.
# 좌표는 사이드카가 로컬 m로 주고 여기서 인치로 바꾼다. 원점·사본 규칙은 scripts/sketchup_baker.py.
# 사용자에게 보이는 Ruby 문구는 영어 하나다(번역 사전 i18n.json은 사이드카 몫 — 패널 문구는 사이드카가 tr()로 만든다).
# EntitiesBuilder(구멍 있는 면·빠른 일괄 생성)가 SketchUp 2022부터라 그 아래는 받지 않는다.

require "json"
require "fileutils"
require "socket"

module BSH
  module Gorani
    ROOT = File.dirname(__FILE__.dup.force_encoding("UTF-8"))   # Windows에서 경로에 한글(사용자 이름)이 있으면 __FILE__ 인코딩이 틀려 번들 파이썬을 못 찾는다(rubocop-sketchup FileEncoding, EW 검사 2026-10-22)
    DICT = "Gorani"                      # 속성 사전 — 모델(원점)·대상지 그룹·항목 그룹
    MANAGED_KEY = "GORANI_MANAGED"       # constants.UDT_MANAGED_KEY
    LOT_KEY = "GORANI_LOT_KEY"           # constants.UDT_LOT_KEY
    LAYER_KEY = "GORANI_LAYER"           # 항목 그룹의 레이어(태그) 이름
    TAG_FOLDER = "CTX"                      # constants.CTX_ROOT_LAYER
    M = 1.m.to_f                            # m → 인치
    DEBUG = false                           # true면 실패를 Ruby 콘솔에도(EW 요건 'Printing to the Console' — 평소에는 패널·사이드카 로그로만)
    RPC = %w[get_model_attrs set_model_attrs clear bake ref save zoom import pick_curve].freeze
    TERRAIN_SMOOTH = Geom::PolygonMesh::AUTO_SOFTEN | Geom::PolygonMesh::SMOOTH_SOFT_EDGES
    HIDDEN_EDGE_LAYER = "CTX::Roads::marking_"   # 테두리 선을 숨기는 레이어(태그) 앞부분
    # 모서리를 살리는 레이어 — 지형처럼 다 부드럽게 하면 교각·난간·옹벽 상자가 둥글게 뭉개졌다(Windows SketchUp 2027, 2026-11-13).
    # 이 레이어는 거의 평평한 이음매(CRISP_ANGLE 미만 — 상판 윗면 삼각형)만 부드럽게 한다
    CRISP_LAYERS = %w[CTX::Bridges CTX::Buildings::parapet CTX::Walls CTX::Rail::platform CTX::Rail::roof CTX::Roads::curb].freeze
    CRISP_ANGLE = 20.degrees
    LOG_DIR = File.join(Dir.home, "Gorani")   # 사이드카 constants.HOME_DIR과 같은 자리
    SIDECAR_START_SECONDS = 90   # 사이드카가 주소를 줄 때까지 기다리는 상한(타이머로 — SketchUp을 막지 않는다). 첫 실행은 백신 검사·.pyc 읽기로 느리다
    # 사이드카가 주소를 주기 전 창에 보이는 화면 — 패널(DESIGN.md)과 같은 색·글꼴. Ruby 문구는 영어 하나(번역 사전은 사이드카 몫)
    STARTING_HTML = <<~HTML
      <!doctype html><html><head><meta charset="utf-8"><style>
      :root { color-scheme: light dark; --paper: #f5f6f8; --ink: #111418; --ink3: #7d8798; --accent: #0057ff; --track: #e5e8ed; }
      @media (prefers-color-scheme: dark) { :root { --paper: #0c1016; --ink: #e8ecf2; --ink3: #7f8a9c; --accent: #5b8bff; --track: #252d38; } }
      html, body { height: 100%; margin: 0; background: var(--paper); color: var(--ink); font: 13px/20px "Segoe UI", -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; }
      main { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 0 32px; text-align: center; }
      b { font-size: 15px; font-weight: 600; } p { margin: 0; color: var(--ink3); font-size: 12px; } code { font-size: 11px; word-break: break-all; color: var(--ink3); }
      .bar { width: 160px; height: 4px; border-radius: 2px; background: var(--track); overflow: hidden; margin-top: 8px; }
      .bar i { display: block; width: 40%; height: 100%; border-radius: 2px; background: var(--accent); animation: go 1.2s ease-in-out infinite; }
      @keyframes go { from { transform: translateX(-100%); } to { transform: translateX(250%); } }
      </style></head><body><main><b>Starting Gorani</b><p>The first start can take up to a minute.</p><div class="bar"><i></i></div></main></body></html>
    HTML

    @wrappers ||= {}   # lot_key → 대상지 그룹. 사이드카(@pid·@io·@url)·패널(@dialog)·마지막 그룹(@last_wrapper)도 모듈 변수 — 다시 읽어도 이어 쓴다

    # ── 사이드카·패널 ─────────────────────────────────────

    def self.python_path
      dir = File.join(ROOT, "python")
      return File.join(dir, "win-x64", "pythonw.exe") if Sketchup.platform == :platform_win
      File.join(dir, RUBY_PLATFORM.start_with?("arm64") ? "mac-arm64" : "mac-x64", "bin", "python3.12")
    end

    def self.sidecar_alive?
      @pid && Process.waitpid(@pid, Process::WNOHANG).nil?
    rescue Errno::ECHILD
      false
    end

    # 사이드카를 띄우기만 한다 — 주소는 poll_start가 타이머로 읽는다(기다리며 SketchUp을 붙잡지 않는다)
    def self.start_sidecar
      python = python_path
      raise "Bundled Python not found: #{python}" unless File.exist?(python)
      File.chmod(0o755, python) unless File.executable?(python)   # 압축을 풀며 실행 권한을 잃는 경우
      FileUtils.mkdir_p(LOG_DIR)
      @log = File.join(LOG_DIR, "sketchup_sidecar.log")
      script = File.join(ROOT, "scripts", "cmd_sketchup.py")
      args = [python, "-I", "-B", "-X", "utf8", script, Sketchup.version]
      @url, @url_buffer = "", +""
      if Sketchup.platform == :platform_win
        # 창 없는 pythonw.exe에는 IO.popen 파이프가 닿지 않는다(사이드카 sys.stdout·stdin = None, 2026-11-05 사용자 로그).
        # stdout을 파일로 돌려도 닿지 않았다(2026-11-06: 주소가 로그에만) — 주소 파일 경로를 인자로 넘겨 사이드카가 직접 쓴다.
        # 알림은 HTTP(tell_sidecar), SketchUp 종료는 사이드카가 이 프로세스 번호로 안다
        @url_file = File.join(LOG_DIR, "sketchup_sidecar.url")
        File.delete(@url_file) if File.exist?(@url_file)
        @io = nil
        @pid = Process.spawn(*args, Process.pid.to_s, @url_file, err: [@log, "w"])
      else
        @url_file = nil
        @io = IO.popen(args, "r+", err: [@log, "w"])
        @io.sync = true
        @pid = @io.pid
      end
      @start_deadline = Time.now + SIDECAR_START_SECONDS
    end

    # 타이머마다 한 번 — 막지 않고 본다. 주소가 나왔으면 그 주소, 아니면 nil
    def self.read_sidecar_url
      if @url_file
        line = File.exist?(@url_file) ? File.read(@url_file).lines.first.to_s.strip : ""
      else
        if IO.select([@io], nil, nil, 0)
          chunk = @io.read_nonblock(4096, exception: false)
          @url_buffer << chunk if chunk.is_a?(String)
        end
        line = @url_buffer.include?("\n") ? @url_buffer.lines.first.strip : ""
      end
      line.start_with?("http://127.0.0.1:") ? line : nil
    end

    # 버튼 → 창부터 띄운다. 사이드카가 이미 떠 있으면 그 주소, 아니면 '시작하는 중' 화면을 보이고 poll_start가 주소로 바꾼다.
    # 첫 실행(Windows 백신 검사·.pyc 읽기)이 수십 초라 그동안 SketchUp을 붙잡으면 '응답 없음'이 됐다(2026-11-06 — 강제 종료로 툴바 배치가 날아갔다)
    def self.show_panel
      raise "Gorani needs SketchUp 2022 or later" if Sketchup.version.to_i < 22   # EntitiesBuilder
      unless @dialog && @dialog.visible?
        @dialog = UI::HtmlDialog.new(dialog_title: "Gorani", preferences_key: "BSH_Gorani", scrollable: true, resizable: true,
                                     width: 480, height: 900, min_width: 380, min_height: 500, style: UI::HtmlDialog::STYLE_DIALOG)
        @dialog.add_action_callback("host_call") { |_context, json| host_call(json) }
        @dialog.set_on_closed { tell_sidecar("panel_closed") }
        @dialog_url = nil
      end
      if !@starting && sidecar_alive? && @url.to_s.start_with?("http://127.0.0.1:")
        @dialog.set_url(@url) unless @dialog_url == @url
        @dialog_url = @url
      else
        unless @starting
          start_sidecar
          @starting = true
          @start_timer = UI.start_timer(0.25, true) { poll_start }
        end
        @dialog.set_html(STARTING_HTML) unless @dialog_url == :starting
        @dialog_url = :starting
      end
      @dialog.visible? ? @dialog.bring_to_front : @dialog.show
    rescue StandardError => e
      stop_start_timer
      UI.messagebox("Could not open Gorani.\n#{e.message}")
    end

    def self.poll_start
      url = read_sidecar_url
      if url
        stop_start_timer
        @url = url
        @dialog.set_url(url)
        @dialog_url = url
      elsif !sidecar_alive? || Time.now > @start_deadline
        stop_start_timer
        @dialog.set_html(get_failed_html(@log))
        @dialog_url = nil
      end
    rescue StandardError => e
      stop_start_timer
      @dialog.set_html(get_failed_html(@log, e.message)) if @dialog
    end

    def self.stop_start_timer
      UI.stop_timer(@start_timer) if @start_timer
      @start_timer = nil
      @starting = false
    end

    def self.get_failed_html(log, detail = nil)
      esc = ->(text) { text.to_s.gsub("&", "&amp;").gsub("<", "&lt;").gsub(">", "&gt;") }
      STARTING_HTML.sub(%r{<main>.*</main>}m, "<main><b>Gorani could not start</b><p>See the log file:</p><code>#{esc.call(log)}</code>" +
                        (detail ? "<p>#{esc.call(detail)}</p>" : "") + "<p>Close this window and press the Gorani button again.</p></main>")
    end

    # 패널을 거치지 않는 알림 — 사이드카 stdin 한 줄(cmd_sketchup._read_parent). 패널을 닫으면 생성을 멈추고 기다리던 호스트 호출을 끝낸다
    def self.tell_sidecar(cmd)
      return unless sidecar_alive?
      if @io
        @io.puts(JSON.generate(cmd: cmd))
      else   # Windows — stdin이 없다. 패널 주소의 POST /cmd(panel_server.DIRECT_CMDS).
        # net/http는 OpenSSL을 끌어와 SketchUp(특히 Windows)에서 느리다(rubocop-sketchup SketchupPerformance/OpenSSL, EW 요건 점검 2026-11-08) — 로컬 소켓으로 직접
        port, token = @url.match(%r{\Ahttp://127\.0\.0\.1:(\d+)/\?token=([^\s&]+)})&.captures
        return unless port
        body = JSON.generate(cmd: cmd)
        Socket.tcp("127.0.0.1", port.to_i, connect_timeout: 2) do |sock|
          sock.write("POST /cmd?token=#{token} HTTP/1.0\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n" \
                     "Content-Length: #{body.bytesize}\r\n\r\n#{body}")
          sock.close_write
          sock.read if IO.select([sock], nil, nil, 5)   # 서버가 답하고 닫을 때까지(HTTP/1.0)
        end
      end
    rescue StandardError
      nil
    end

    def self.host_call(json)
      msg = JSON.parse(json)
      raise ArgumentError, "Unknown call: #{msg['method']}" unless RPC.include?(msg["method"])
      reply(msg["id"], true, send("rpc_#{msg['method']}", msg["args"] || {}), "")
    rescue StandardError => e
      warn "[Gorani] #{e.class}: #{e.message}\n#{e.backtrace.first(5).join("\n")}" if DEBUG
      reply(msg && msg["id"], false, nil, "#{e.class}: #{e.message}")
    end

    def self.reply(id, ok, result, error)
      payload = { cmd: "host_reply", id: id, ok: ok, result: result, error: error }
      @dialog.execute_script("send(#{JSON.generate(payload)})") if @dialog
    end

    # ── 모델 속성·지우기 ──────────────────────────────────

    def self.rpc_get_model_attrs(args)
      model = Sketchup.active_model
      args["keys"].map { |key| model.get_attribute(DICT, key) }
    end

    def self.rpc_set_model_attrs(args)
      model = Sketchup.active_model
      model.start_operation("Gorani", true, false, true)
      args["values"].each { |key, value| model.set_attribute(DICT, key, value) }
      model.commit_operation
      true
    end

    def self.managed?(entity, lot_key = nil)
      return false unless entity.is_a?(Sketchup::Group) || entity.is_a?(Sketchup::ComponentInstance)
      return false unless entity.get_attribute(DICT, MANAGED_KEY) == "1"
      lot_key.nil? || entity.get_attribute(DICT, LOT_KEY) == lot_key
    end

    # 같은 대상지의 앞 결과 지우기 — 한 번의 생성·다시 넣기가 Undo 한 번이 되도록 여기서 작업을 열고 뒤 호출은 이어 붙인다
    def self.rpc_clear(args)
      model = Sketchup.active_model
      targets = model.entities.select { |e| managed?(e, args["lot_key"]) }
      model.start_operation("Gorani", true)
      model.entities.erase_entities(targets) unless targets.empty?
      model.commit_operation
      @wrappers.delete(args["lot_key"])
      [targets.size, 0]
    end

    # ── 태그·재질 ─────────────────────────────────────────

    def self.get_tag(model, name, rgb, hidden)
      tag = model.layers[name]
      return tag if tag
      tag = model.layers.add(name)
      tag.color = Sketchup::Color.new(*rgb)
      tag.visible = false if hidden
      folder = model.layers.folders.find { |f| f.name == TAG_FOLDER } || model.layers.add_folder(TAG_FOLDER)
      tag.folder = folder
      tag
    end

    def self.get_material(model, name, rgb)
      material = model.materials[name] || model.materials.add(name)
      material.color = Sketchup::Color.new(*rgb)
      material
    end

    def self.set_attrs(entity, attrs)
      (attrs || {}).each { |key, value| entity.set_attribute(DICT, key, value.to_s) }
    end

    # ── 베이크 ────────────────────────────────────────────

    def self.get_wrapper(model, lot_key, lot_name, shift)
      wrapper = @wrappers[lot_key]
      return wrapper if wrapper && wrapper.valid?
      wrapper = model.entities.add_group
      wrapper.name = "Gorani #{lot_name}"
      wrapper.set_attribute(DICT, MANAGED_KEY, "1")
      wrapper.set_attribute(DICT, LOT_KEY, lot_key)
      wrapper.transformation = Geom::Transformation.translation(Geom::Vector3d.new(shift[0] * M, shift[1] * M, 0))
      @wrappers[lot_key] = wrapper
    end

    def self.point(x, y, z)
      Geom::Point3d.new(x * M, y * M, z * M)
    end

    def self.add_mesh(entities, verts, faces, hide_edges = false, crisp = false)
      mesh = Geom::PolygonMesh.new(verts.size, faces.size)
      index = verts.map { |x, y, z| mesh.add_point(point(x, y, z)) }   # 같은 자리 점은 앞 번호를 돌려준다
      faces.each do |face|
        ids = face.map { |i| index[i] }
        mesh.add_polygon(*ids) if ids.uniq.size >= 3
      end
      entities.fill_from_mesh(mesh, true, crisp ? 0 : TERRAIN_SMOOTH)
      if crisp
        entities.grep(Sketchup::Edge).each do |edge|
          pair = edge.faces
          next unless pair.size == 2 && pair[0].normal.angle_between(pair[1].normal) < CRISP_ANGLE
          edge.soft = true
          edge.smooth = true
        end
      end
      # 노면표시 — 15 cm 띠의 테두리 선이 면보다 굵게 그려져 차선이 검은 점선으로 보였다(Windows SketchUp 2027, 2026-11-08)
      entities.grep(Sketchup::Edge).each { |edge| edge.hidden = true } if hide_edges
    end

    # 동 하나 = 그룹 하나. 파트마다 바닥(아래를 본다)·지붕·옆면. 링은 전부 반시계 — 옆면은 구멍 링을 뒤집어 법선이 바깥(구멍 쪽)을 보게 한다
    def self.add_prisms(entities, prisms)
      failed = 0
      prisms.each do |parts, base, height, attrs, name|
        group = entities.add_group
        group.name = name.to_s unless name.to_s.empty?
        set_attrs(group, attrs)
        group.entities.build do |builder|
          parts.each do |rings|
            bottom = rings.map { |ring| ring.map { |x, y| point(x, y, base) } }
            top = rings.map { |ring| ring.map { |x, y| point(x, y, base + height) } }
            builder.add_face(bottom[0].reverse, holes: bottom[1..-1])
            builder.add_face(top[0], holes: top[1..-1])
            bottom.each_index do |k|
              lo, hi = k.zero? ? [bottom[k], top[k]] : [bottom[k].reverse, top[k].reverse]
              lo.each_index { |i| j = (i + 1) % lo.size; builder.add_face(lo[i], lo[j], hi[j], hi[i]) }
            end
          end
        end
      rescue ArgumentError => e   # 자기교차 발자국 등
        failed += 1
        warn "[Gorani] building #{name}: #{e.message}" if DEBUG
        group.erase! if group && group.valid?
      end
      failed
    end

    def self.add_polylines(entities, polylines)
      entities.build do |builder|
        polylines.each do |pts, closed|
          points = pts.map { |x, y, z| point(x, y, z) }
          points << points.first if closed
          builder.add_edges(points) if points.size >= 2
        end
      end
    end

    def self.rpc_bake(args)
      data = JSON.parse(File.read(args["path"], encoding: "UTF-8"))
      model = Sketchup.active_model
      model.start_operation("Gorani", true, false, true)
      wrapper = get_wrapper(model, data["lot_key"], data["lot_name"], data["shift"])
      @last_wrapper = wrapper
      ids = []
      data["items"].each do |item|
        group = wrapper.entities.add_group
        group.name = item["name"].to_s
        group.layer = get_tag(model, item["layer"], item["rgb"], item["hidden"])
        group.material = get_material(model, item["layer"], item["rgb"])
        group.set_attribute(DICT, LAYER_KEY, item["layer"])
        set_attrs(group, item["attrs"])
        if !item["faces"].empty?
          add_mesh(group.entities, item["verts"], item["faces"], item["layer"].start_with?(HIDDEN_EDGE_LAYER),
                   CRISP_LAYERS.any? { |layer| item["layer"].start_with?(layer) })
        elsif !item["prisms"].empty?
          add_prisms(group.entities, item["prisms"])
        else
          add_polylines(group.entities, item["polylines"])
        end
        ids << group.persistent_id
      rescue StandardError => e
        warn "[Gorani] #{item['layer']} #{item['name']}: #{e.message}" if DEBUG
      end
      model.commit_operation
      ids
    end

    def self.rpc_ref(args)
      model = Sketchup.active_model
      model.start_operation("Gorani", true, false, true)
      wrapper = get_wrapper(model, args["lot_key"], args["lot_name"], args["shift"])
      group = wrapper.entities.add_group
      group.name = "origin"
      group.layer = get_tag(model, args["layer"], args["rgb"], false)
      group.set_attribute(DICT, LAYER_KEY, args["layer"])
      set_attrs(group, args["attrs"])
      cpoint = group.entities.add_cpoint(ORIGIN)
      text = group.entities.add_text(args["label"], ORIGIN)
      model.commit_operation
      [cpoint.persistent_id, text.persistent_id]
    end

    def self.rpc_save(args)
      raise "No site group to save" unless @last_wrapper && @last_wrapper.valid?
      raise "Could not write context.skp: #{args['path']}" unless @last_wrapper.definition.save_copy(args["path"])
      @last_wrapper.entities.size
    end

    # ── 다시 넣기·줌·커브 ─────────────────────────────────

    def self.rpc_import(args)
      model = Sketchup.active_model
      model.start_operation("Gorani", true, false, true)
      definition = model.definitions.load(args["path"])
      shift = args["shift"]
      instance = model.entities.add_instance(definition, Geom::Transformation.translation(Geom::Vector3d.new(shift[0] * M, shift[1] * M, 0)))
      instance.name = "Gorani #{args['lot_name']}"
      instance.set_attribute(DICT, MANAGED_KEY, "1")
      instance.set_attribute(DICT, LOT_KEY, args["lot_key"].to_s)
      model.commit_operation
      @wrappers[args["lot_key"]] = instance
      tags = definition.entities.map(&:layer).uniq
      { "objects" => definition.entities.size, "layers" => tags.size }
    end

    # 남서쪽 위에서 bounds가 화면 너비에 들어오게 본다(Rhino ZoomBoundingBox처럼 범위로 거리를 정한다). z = 바라볼 높이
    def self.look_at(view, bounds, z)
      target = Geom::Point3d.new(bounds.center.x, bounds.center.y, z)
      camera = Sketchup::Camera.new   # 투시, 세로 시야 30°
      half = Math.atan(Math.tan(camera.fov.degrees / 2) * view.vpwidth / view.vpheight)   # 가로 시야 반각
      offset = Geom::Vector3d.new(-0.6, -1.0, 2.0)   # 남남서 위 60° — 낮으면 도심 고층 건물이 대상지를 가린다(을지로1가 87 시험)
      offset.length = [bounds.width, bounds.height].max / 2 / Math.tan(half)
      camera.set(target.offset(offset), target, Z_AXIS)
      view.camera = camera
    end

    # 대상지(CTX::Site) + 사방 대각선 반 여백(Rhino zoom_to_site와 같다, 한 변 min_span 이상), 대상지가 없으면(위치 방식) box = 중심 ± half.
    # 바라볼 높이는 지형 가운데 — 대상지 선은 Z = 0이고 지형은 표고 그대로다
    def self.rpc_zoom(args)
      model = Sketchup.active_model
      wrapper = @wrappers[args["lot_key"]] if args["lot_key"]
      wrapper ||= model.entities.find { |e| managed?(e, args["lot_key"]) } if args["lot_key"]
      wrapper = nil unless wrapper && wrapper.valid?
      items = wrapper ? wrapper.definition.entities.to_a : []
      site = items.find { |e| e.get_attribute(DICT, LAYER_KEY) == "#{TAG_FOLDER}::Site" }
      terrain = items.find { |e| e.get_attribute(DICT, LAYER_KEY) == "#{TAG_FOLDER}::Terrain" }
      z = terrain ? terrain.bounds.center.transform(wrapper.transformation).z : 0
      bounds = Geom::BoundingBox.new
      if site
        8.times { |i| bounds.add(site.bounds.corner(i).transform(wrapper.transformation)) }
        margin = [bounds.diagonal / 2, (args["min_span"].to_f * M - [bounds.width, bounds.height].max) / 2].max
        bounds.add(bounds.min.offset([-margin, -margin, 0]), bounds.max.offset([margin, margin, 0]))
      elsif args["box"]
        x, y, half = args["box"]
        bounds.add(point(x - half, y - half, 0), point(x + half, y + half, 0))
      else
        return false
      end
      look_at(model.active_view, bounds, z)
      true
    end

    # 패널 '해와 그림자' — 그림자 설정을 대상지 위경도·그 시간대 시계로 맞추고 그림자를 켠다(on = false면 그림자만 끈다).
    # ShadowTime은 '그 시간대 시계 값을 UTC 필드에 담은' Time이다(SketchUp 관례) — Time.utc(시계)로 넣고 TZOffset으로 시간대를 준다.
    # 모델 +Y = 북(Gorani 베이크와 같다)이라 NorthAngle 0. 해 위치는 SketchUp이 계산한다(사이드카 solar와 0.1° 안팎)
    def self.rpc_sun(args)
      info = Sketchup.active_model.shadow_info
      unless args["on"]
        info["DisplayShadows"] = false
        return true
      end
      year, month, day, hour, minute = args["local"]
      info["Latitude"] = args["lat"].to_f
      info["Longitude"] = args["lng"].to_f
      info["TZOffset"] = args["tz"].to_f
      info["NorthAngle"] = 0.0
      info["ShadowTime"] = Time.utc(year, month, day, hour, minute)
      info["DisplayShadows"] = true
      info["UseSunForAllShading"] = true
      true
    end

    # 면 하나(바깥 고리) 또는 끊김 없이 한 바퀴 도는 선들 → 모델 좌표 m. 그룹을 편집 중이면 편집 변환을 곱한다
    def self.rpc_pick_curve(_args)
      model = Sketchup.active_model
      faces = model.selection.grep(Sketchup::Face)
      edges = model.selection.grep(Sketchup::Edge)
      positions =
        if faces.size == 1
          faces[0].outer_loop.vertices.map(&:position)
        elsif faces.empty? && !edges.empty?
          get_loop(edges)
        end
      return { "ring" => nil } unless positions && positions.size >= 3   # 안내 문구는 사이드카(tr)가 붙인다
      transform = model.edit_transform
      { "ring" => positions.map { |p| q = p.transform(transform); [q.x.to_m, q.y.to_m, q.z.to_m] } }
    end

    def self.get_loop(edges)
      left = edges.drop(1)
      start = edges[0].start
      positions = [start.position]
      vertex = edges[0].end
      until left.empty?
        edge = left.find { |e| e.used_by?(vertex) }
        return nil unless edge
        left.delete(edge)
        positions << vertex.position
        vertex = edge.other_vertex(vertex)
      end
      vertex == start ? positions : nil
    end

    unless file_loaded?(__FILE__)
      command = UI::Command.new("Gorani") { show_panel }
      command.tooltip = "Gorani"
      command.status_bar_text = "Gorani: buildings, roads, terrain and water around your site in 3D, plus basemaps and analysis maps"
      # 아이콘: Windows는 SVG(벡터), macOS는 PNG — 맥 SketchUp의 벡터 아이콘은 PDF뿐이다
      icon = File.join(ROOT, "icons", Sketchup.platform == :platform_win ? "gorani.svg" : "gorani.png")
      command.small_icon = command.large_icon = icon if File.exist?(icon)
      UI.menu("Extensions").add_item(command)
      toolbar = UI::Toolbar.new("Gorani")
      toolbar.add_item(command)
      toolbar.restore
      file_loaded(__FILE__)
    end
  end
end
