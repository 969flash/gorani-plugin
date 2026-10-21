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

module BSH
  module Gorani
    ROOT = File.dirname(__FILE__.dup.force_encoding("UTF-8"))   # Windows에서 경로에 한글(사용자 이름)이 있으면 __FILE__ 인코딩이 틀려 번들 파이썬을 못 찾는다(rubocop-sketchup FileEncoding, EW 검사 2026-10-22)
    DICT = "Gorani"                      # 속성 사전 — 모델(원점)·대상지 그룹·항목 그룹
    MANAGED_KEY = "GORANI_MANAGED"       # constants.UDT_MANAGED_KEY
    LOT_KEY = "GORANI_LOT_KEY"           # constants.UDT_LOT_KEY
    LAYER_KEY = "GORANI_LAYER"           # 항목 그룹의 레이어(태그) 이름
    TAG_FOLDER = "CTX"                      # constants.CTX_ROOT_LAYER
    M = 1.m.to_f                            # m → 인치
    RPC = %w[get_model_attrs set_model_attrs clear bake ref save zoom import pick_curve].freeze
    TERRAIN_SMOOTH = Geom::PolygonMesh::AUTO_SOFTEN | Geom::PolygonMesh::SMOOTH_SOFT_EDGES
    LOG_DIR = File.join(Dir.home, "Gorani")   # 사이드카 constants.HOME_DIR과 같은 자리

    @wrappers ||= {}   # lot_key → 대상지 그룹. 사이드카(@io·@url)·패널(@dialog)·마지막 그룹(@last_wrapper)도 모듈 변수 — 다시 읽어도 이어 쓴다

    # ── 사이드카·패널 ─────────────────────────────────────

    def self.python_path
      dir = File.join(ROOT, "python")
      return File.join(dir, "win-x64", "pythonw.exe") if Sketchup.platform == :platform_win
      File.join(dir, RUBY_PLATFORM.start_with?("arm64") ? "mac-arm64" : "mac-x64", "bin", "python3.12")
    end

    def self.sidecar_alive?
      @io && Process.waitpid(@io.pid, Process::WNOHANG).nil?
    rescue Errno::ECHILD
      false
    end

    def self.sidecar_url
      return @url if sidecar_alive?
      python = python_path
      raise "Bundled Python not found: #{python}" unless File.exist?(python)
      File.chmod(0o755, python) unless File.executable?(python)   # 압축을 풀며 실행 권한을 잃는 경우
      FileUtils.mkdir_p(LOG_DIR)
      log = File.join(LOG_DIR, "sketchup_sidecar.log")
      script = File.join(ROOT, "scripts", "cmd_sketchup.py")
      @io = IO.popen([python, "-I", "-B", "-X", "utf8", script, Sketchup.version], "r+", err: [log, "w"])
      @io.sync = true
      @url = @io.gets.to_s.strip
      raise "The Gorani engine did not start. See #{log}" unless @url.start_with?("http://127.0.0.1:")
      @url
    end

    # 패널을 하나만 띄운다. 사이드카가 죽어 새로 떴으면(주소가 바뀌면) 열린 창도 새 주소로
    def self.show_panel
      raise "Gorani needs SketchUp 2022 or later" if Sketchup.version.to_i < 22   # EntitiesBuilder
      url = sidecar_url
      unless @dialog && @dialog.visible?
        @dialog = UI::HtmlDialog.new(dialog_title: "Gorani", preferences_key: "BSH_Gorani", scrollable: true, resizable: true,
                                     width: 480, height: 900, min_width: 380, min_height: 500, style: UI::HtmlDialog::STYLE_DIALOG)
        @dialog.add_action_callback("host_call") { |_context, json| host_call(json) }
        @dialog.set_on_closed { tell_sidecar("panel_closed") }
        @dialog_url = nil
      end
      @dialog.set_url(url) unless @dialog_url == url
      @dialog_url = url
      @dialog.visible? ? @dialog.bring_to_front : @dialog.show
    rescue StandardError => e
      UI.messagebox("Could not open Gorani.\n#{e.message}")
    end

    # 패널을 거치지 않는 알림 — 사이드카 stdin 한 줄(cmd_sketchup._read_parent). 패널을 닫으면 생성을 멈추고 기다리던 호스트 호출을 끝낸다
    def self.tell_sidecar(cmd)
      @io.puts(JSON.generate(cmd: cmd)) if sidecar_alive?
    rescue IOError, SystemCallError
      nil
    end

    def self.host_call(json)
      msg = JSON.parse(json)
      raise ArgumentError, "Unknown call: #{msg['method']}" unless RPC.include?(msg["method"])
      reply(msg["id"], true, send("rpc_#{msg['method']}", msg["args"] || {}), "")
    rescue StandardError => e
      warn "[Gorani] #{e.class}: #{e.message}\n#{e.backtrace.first(5).join("\n")}"
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

    def self.add_mesh(entities, verts, faces)
      mesh = Geom::PolygonMesh.new(verts.size, faces.size)
      index = verts.map { |x, y, z| mesh.add_point(point(x, y, z)) }   # 같은 자리 점은 앞 번호를 돌려준다
      faces.each do |face|
        ids = face.map { |i| index[i] }
        mesh.add_polygon(*ids) if ids.uniq.size >= 3
      end
      entities.fill_from_mesh(mesh, true, TERRAIN_SMOOTH)
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
        warn "[Gorani] building #{name}: #{e.message}"
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
          add_mesh(group.entities, item["verts"], item["faces"])
        elsif !item["prisms"].empty?
          add_prisms(group.entities, item["prisms"])
        else
          add_polylines(group.entities, item["polylines"])
        end
        ids << group.persistent_id
      rescue StandardError => e
        warn "[Gorani] #{item['layer']} #{item['name']}: #{e.message}"
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
