// Gorani Rhino 7판 본문 — dev_deploy.py rhino7이 Gorani.rhp(net48, RhinoCommon 7.0)로 빌드한다.
//
// Rhino 7에는 CPython 3이 없어(IronPython 2.7뿐) 패키지에 든 번들 파이썬(python/<플랫폼>/)으로 사이드카 scripts/cmd_rhino7.py를 띄운다.
// 사이드카가 첫 줄로 준 127.0.0.1 패널 주소를 연다 — Mac은 Eto WebView 창, Windows는 Edge 앱 창(Rhino 7 Windows의 Eto WebView는 IE 엔진이라
// 패널 JS가 돌지 않는다). 엔진·패널·데이터 받기는 전부 파이썬이고, 여기는 Rhino 문서를 만지는 호스트 호출만 한다:
// 사이드카 stdout 한 줄 = {"type": "host_call", id, method, args} → UI 스레드에서 Rpc → stdin 한 줄 = {"cmd": "host_reply", id, ok, result, error}.
// 호출 이름·인자는 SketchUp판(sketchup_ext.rb)과 같다(사이드카 쪽은 sketchup_baker 그대로). 문서 모양은 Rhino 8판(context_baker)과 같다 —
// CTX::<레이어>의 객체마다 UserString(GORANI_MANAGED·GORANI_LOT_KEY + 속성), 건물은 동마다 Mesh, 원점은 doc.Strings.
// 좌표는 사이드카가 로컬 m로 주고 여기서 계산 원점 − 문서 원점(shift)만큼 옮겨 문서 단위로 바꾼다. 사본 context.3dm은 로컬 좌표(옮기기 전)다.
// 사용자에게 보이는 문구는 영어 하나다(번역은 사이드카 몫 — 패널 문구는 사이드카가 tr()로 만든다).

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using Rhino;
using Rhino.Commands;
using Rhino.DocObjects;
using Rhino.FileIO;
using Rhino.Geometry;
using Rhino.Geometry.Intersect;
using Rhino.PlugIns;

[assembly: Guid("8b0c1f5e-3d0a-4f53-9a6e-2c7e1d4b9a10")]   // dev_deploy.PLUGIN_ID — Rhino 8판과 같다(yak 검색어 guid:)

namespace Gorani
{
    public class GoraniPlugIn : PlugIn
    {
    }

    [Guid("8b0c1f5e-3d0a-4f53-9a6e-2c7e1d4b9a11")]   // dev_deploy.COMMAND_ID
    public class GoraniCommand : Command
    {
        public override string EnglishName => "Gorani";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            try
            {
                Host.ShowPanel();
                return Result.Success;
            }
            catch (Exception e)
            {
                RhinoApp.WriteLine("[Gorani] " + e);
                Rhino.UI.Dialogs.ShowMessage("Gorani could not open.\n" + e.Message, "Gorani");
                return Result.Failure;
            }
        }
    }

    static class Host
    {
        const string ManagedKey = "GORANI_MANAGED";   // constants.UDT_MANAGED_KEY
        const string LotKey = "GORANI_LOT_KEY";       // constants.UDT_LOT_KEY
        const string RootLayer = "CTX";               // constants.CTX_ROOT_LAYER

        static readonly string Root = Path.GetDirectoryName(typeof(Host).Assembly.Location);   // yak 설치 폴더(Gorani.rhp 옆에 python/·scripts/)
        static readonly string LogDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Gorani");   // 사이드카 constants.HOME_DIR과 같은 자리
        static readonly object WriteLock = new object();
        static readonly string LogPath = Path.Combine(LogDir, "rhino7_sidecar.log");
        static TextWriter log;   // 한 번만 연다 — 사이드카를 다시 띄울 때 다시 열면 Windows는 앞 핸들 때문에 실패한다
        static Process sidecar;
        static string url;
        static Eto.Forms.Form panel;
        static string panelUrl;
        static List<Guid> lastIds = new List<Guid>();   // 마지막 대상지로 구운 객체 — save가 context.3dm으로 쓴다
        static double[] lastShift = { 0.0, 0.0 };

        // ── 사이드카·패널 ─────────────────────────────────────

        static IEnumerable<string> GetPythonPaths()
        {
            string dir = Path.Combine(Root, "python");
            if (Rhino.Runtime.HostUtils.RunningOnWindows)
            {
                yield return Path.Combine(dir, "win-x64", "python.exe");
                yield break;
            }
            // Apple Silicon이면 arm64 — Intel Mac에서는 arm64 실행 파일이 뜨지 않아 다음 후보(x64)로 넘어간다
            yield return Path.Combine(dir, "mac-arm64", "bin", "python3.12");
            yield return Path.Combine(dir, "mac-x64", "bin", "python3.12");
        }

        static string GetSidecarUrl()
        {
            if (sidecar != null && !sidecar.HasExited && url != null)
                return url;
            Directory.CreateDirectory(LogDir);
            string script = Path.Combine(Root, "scripts", "cmd_rhino7.py");
            log = log ?? TextWriter.Synchronized(new StreamWriter(LogPath, false, new UTF8Encoding(false)) { AutoFlush = true });
            var errors = new List<string>();
            foreach (string python in GetPythonPaths().Where(File.Exists))
            {
                try
                {
                    if (!Rhino.Runtime.HostUtils.RunningOnWindows)   // yak이 압축을 풀며 실행 권한을 잃는다
                        Process.Start("/bin/chmod", "755 \"" + python + "\"")?.WaitForExit();
                    var info = new ProcessStartInfo(python, string.Format("-I -B -X utf8 \"{0}\" \"{1}\"", script, RhinoApp.Version))
                    {
                        UseShellExecute = false, CreateNoWindow = true,
                        RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                        StandardOutputEncoding = new UTF8Encoding(false), StandardErrorEncoding = new UTF8Encoding(false),
                    };
                    var process = Process.Start(info);
                    process.ErrorDataReceived += (s, e) => { if (e.Data != null) log.WriteLine(e.Data); };
                    process.BeginErrorReadLine();
                    string first = process.StandardOutput.ReadLine();
                    if (first == null || !first.StartsWith("http://127.0.0.1:"))
                    {
                        errors.Add(python + ": " + (first ?? "exited"));
                        if (!process.HasExited)
                            process.Kill();
                        continue;
                    }
                    sidecar = process;
                    url = first.Trim();
                    new Thread(() => ReadSidecar(process)) { IsBackground = true, Name = "gorani-sidecar" }.Start();
                    return url;
                }
                catch (Exception e)   // 이 CPU에서 못 도는 실행 파일 등
                {
                    errors.Add(python + ": " + e.Message);
                }
            }
            // 파이썬이 없으면 Rhino를 끄지 않고 업데이트해 옛 판 폴더가 지워진 경우가 많다(Rhino 8판 0.3.5 사용자 신고와 같은 상황)
            throw new InvalidOperationException("The bundled Python did not start. Log: " + LogPath
                                                + (errors.Count > 0 ? "\n" + string.Join("\n", errors) : "\nIf you just updated Gorani, restart Rhino."));
        }

        // 사이드카 stdout 한 줄마다 UI 스레드에서 호출을 처리한다. 끝나면(사이드카가 죽음) 다음 Gorani 명령이 새로 띄운다
        static void ReadSidecar(Process process)
        {
            string line;
            while ((line = process.StandardOutput.ReadLine()) != null)
            {
                string call = line;
                RhinoApp.InvokeOnUiThread(new Action(() => Handle(call)));
            }
        }

        static void Tell(object message)
        {
            lock (WriteLock)
            {
                if (sidecar == null || sidecar.HasExited)
                    return;
                sidecar.StandardInput.WriteLine(Json.Write(message));
                sidecar.StandardInput.Flush();
            }
        }

        public static void ShowPanel()
        {
            string address = GetSidecarUrl();
            if (Rhino.Runtime.HostUtils.RunningOnWindows)
            {
                try   // Windows 10·11에는 Edge가 늘 있다 — 앱 창(주소창 없음)
                {
                    Process.Start(new ProcessStartInfo("msedge.exe", "--app=\"" + address + "\" --window-size=480,900") { UseShellExecute = true });
                }
                catch (Exception)
                {
                    Process.Start(new ProcessStartInfo(address) { UseShellExecute = true });
                }
                return;
            }
            if (panel != null && panel.Visible)
            {
                if (panelUrl != address)   // 사이드카가 새로 떴으면 새 주소로
                    ((Eto.Forms.WebView)panel.Content).Url = new Uri(address);
                panelUrl = address;
                panel.BringToFront();
                return;
            }
            panel = new Eto.Forms.Form
            {
                Title = "Gorani", ClientSize = new Eto.Drawing.Size(480, 900), Resizable = true,
                Content = new Eto.Forms.WebView { Url = new Uri(address) },
            };
            panelUrl = address;
            panel.Closed += (s, e) => { panel = null; Tell(new Dictionary<string, object> { { "cmd", "panel_closed" } }); };   // 생성 중이면 취소
            panel.Show();
        }

        static void Handle(string line)
        {
            object id = null;
            try
            {
                var message = (Dictionary<string, object>)Json.Parse(line);
                id = message["id"];
                var args = message.ContainsKey("args") ? (Dictionary<string, object>)message["args"] : new Dictionary<string, object>();
                RhinoDoc doc = RhinoDoc.ActiveDoc ?? throw new InvalidOperationException("No open Rhino document");
                Tell(Reply(id, true, Rpc(doc, (string)message["method"], args), ""));
            }
            catch (Exception e)
            {
                RhinoApp.WriteLine("[Gorani] " + e);
                Tell(Reply(id, false, null, e.GetType().Name + ": " + e.Message));
            }
        }

        static Dictionary<string, object> Reply(object id, bool ok, object result, string error)
        {
            return new Dictionary<string, object> { { "cmd", "host_reply" }, { "id", id }, { "ok", ok }, { "result", result }, { "error", error } };
        }

        static object Rpc(RhinoDoc doc, string method, Dictionary<string, object> args)
        {
            switch (method)
            {
                case "get_model_attrs":
                    return L(args["keys"]).Select(key => (object)doc.Strings.GetValue((string)key)).ToList();
                case "set_model_attrs":
                    foreach (var pair in (Dictionary<string, object>)args["values"])
                        doc.Strings.SetString(pair.Key, (string)pair.Value);
                    return true;
                case "clear": return Clear(doc, args["lot_key"] as string);
                case "bake": return Bake(doc, (Dictionary<string, object>)Json.Parse(File.ReadAllText((string)args["path"], Encoding.UTF8)));
                case "ref": return AddRef(doc, args);
                case "save": return Save(doc, (string)args["path"]);
                case "import": return Import(doc, args);
                case "zoom": return Zoom(doc, args);
                case "pick_curve": return PickCurve(doc, D(args["tolerance"]));
                default: throw new ArgumentException("Unknown call: " + method);
            }
        }

        // ── 단위·레이어 ───────────────────────────────────────

        static double GetUnitScale(RhinoDoc doc)
        {
            UnitSystem units = doc.ModelUnitSystem;
            if (units == UnitSystem.None || units == UnitSystem.CustomUnits || units == UnitSystem.Unset)
                throw new InvalidOperationException("Set the Rhino document units to mm, cm or m");
            return RhinoMath.UnitScale(UnitSystem.Meters, units);
        }

        // 로컬 m → 문서: shift만큼 옮기고(A*B는 B 먼저) 문서 단위로
        static Transform GetPlacement(double[] shift, double scale)
        {
            return Transform.Scale(Point3d.Origin, scale) * Transform.Translation(shift[0], shift[1], 0.0);
        }

        // 'CTX::Buildings'를 부모부터 만들고 최하위 인덱스(context_baker._ensure_layer와 같다). 색은 이미 있는 레이어에도 다시 넣는다
        static int EnsureLayer(RhinoDoc doc, string fullPath, System.Drawing.Color color, bool hidden, Dictionary<string, int> cache)
        {
            string[] names = fullPath.Split(new[] { "::" }, StringSplitOptions.None);
            Guid parent = Guid.Empty;
            int index = -1;
            for (int depth = 0; depth < names.Length; depth++)
            {
                string path = string.Join("::", names, 0, depth + 1);
                if (!cache.TryGetValue(path, out index))
                {
                    index = doc.Layers.FindByFullPath(path, -1);
                    if (index >= 0 && doc.Layers[index].IsDeleted)   // 지운 레이어도 이름으로 찾힌다
                        index = -1;
                    if (index < 0)
                    {
                        var layer = new Layer { Name = names[depth] };
                        if (parent != Guid.Empty)
                            layer.ParentLayerId = parent;
                        if (depth == names.Length - 1 && hidden)
                            layer.IsVisible = false;
                        index = doc.Layers.Add(layer);
                        if (index < 0)
                            throw new InvalidOperationException("Could not create layer " + path);
                    }
                    cache[path] = index;
                }
                parent = doc.Layers[index].Id;
            }
            if (doc.Layers[index].Color.ToArgb() != color.ToArgb())
                doc.Layers[index].Color = color;
            return index;
        }

        static RhinoObject[] GetAllObjects(RhinoDoc doc)
        {
            var settings = new ObjectEnumeratorSettings { HiddenObjects = true, LockedObjects = true, IncludeLights = false, IncludeGrips = false };
            return doc.Objects.GetObjectList(settings).ToArray();
        }

        // ── 지우기·베이크 ─────────────────────────────────────

        // 이 도구의 객체(lot_key를 주면 그 대상지만) + 빈 CTX 레이어 삭제(context_baker.clear_previous). 출력 [객체 수, 레이어 수]
        static object Clear(RhinoDoc doc, string lotKey)
        {
            var settings = new ObjectEnumeratorSettings { HiddenObjects = true, LockedObjects = true };
            RhinoObject[] found = doc.Objects.FindByUserString(lotKey != null ? LotKey : ManagedKey, lotKey ?? "1", true, false, true, settings) ?? new RhinoObject[0];
            int deleted = 0, layers = 0;
            bool redraw = doc.Views.RedrawEnabled;
            doc.Views.RedrawEnabled = false;
            try
            {
                foreach (RhinoObject rhinoObject in found)
                    if (rhinoObject.Attributes.GetUserString(ManagedKey) == "1" && doc.Objects.Delete(rhinoObject, true, true))
                        deleted++;
                var indexes = doc.Layers.Where(l => !l.IsDeleted && (l.FullPath == RootLayer || l.FullPath.StartsWith(RootLayer + "::")))
                                        .OrderByDescending(l => l.FullPath.Split(new[] { "::" }, StringSplitOptions.None).Length).Select(l => l.Index).ToList();
                if (indexes.Contains(doc.Layers.CurrentLayerIndex))
                    doc.Layers.SetCurrentLayerIndex(0, true);
                foreach (int index in indexes)   // 깊은 것부터 — 자식을 먼저 지워야 부모가 비는지 안다
                {
                    Layer layer = doc.Layers[index];
                    if ((layer.GetChildren() ?? new Layer[0]).Length > 0 || (doc.Objects.FindByLayer(layer) ?? new RhinoObject[0]).Length > 0)
                        continue;
                    if (doc.Layers.Delete(index, true))
                        layers++;
                }
            }
            finally
            {
                doc.Views.RedrawEnabled = redraw;
            }
            lastIds = new List<Guid>();
            return new List<object> { deleted, layers };
        }

        static Guid AddObject(RhinoDoc doc, GeometryBase geometry, Transform placement, bool moved, int layerIndex, string name,
                              Dictionary<string, object> attrs, string lotKey)
        {
            if (moved && geometry is Mesh mesh)   // 단정밀도 정점은 서울 좌표(55만 m)에서 6 cm 단위로 뭉개진다
                mesh.Vertices.UseDoublePrecisionVertices = true;
            if (!placement.IsIdentity)
                geometry.Transform(placement);
            ObjectAttributes attributes = doc.CreateDefaultAttributes();
            attributes.LayerIndex = layerIndex;
            if (!string.IsNullOrEmpty(name))
                attributes.Name = name;
            foreach (var pair in attrs ?? new Dictionary<string, object>())
                attributes.SetUserString(pair.Key, pair.Value == null ? "" : Convert.ToString(pair.Value, CultureInfo.InvariantCulture));
            attributes.SetUserString(ManagedKey, "1");
            attributes.SetUserString(LotKey, lotKey);
            Guid id = doc.Objects.Add(geometry, attributes);
            if (id != Guid.Empty)
                lastIds.Add(id);
            return id;
        }

        static Mesh GetMesh(List<object> verts, List<object> faces)
        {
            var mesh = new Mesh();
            foreach (object vert in verts)
            {
                List<object> v = L(vert);
                mesh.Vertices.Add(D(v[0]), D(v[1]), D(v[2]));
            }
            foreach (object face in faces)
            {
                List<object> f = L(face);
                if (f.Count == 3)
                    mesh.Faces.AddFace(I(f[0]), I(f[1]), I(f[2]));
                else if (f.Count == 4)
                    mesh.Faces.AddFace(I(f[0]), I(f[1]), I(f[2]), I(f[3]));
            }
            mesh.Normals.ComputeNormals();
            mesh.Compact();
            return mesh;
        }

        static PolylineCurve GetRingCurve(List<object> ring, double z)
        {
            var points = ring.Select(p => new Point3d(D(L(p)[0]), D(L(p)[1]), z)).ToList();
            points.Add(points[0]);
            return new PolylineCurve(points);
        }

        // 동 하나(파트마다 외곽 링 + 구멍 링, 로컬 m) → 닫힌 Mesh 하나(context_geometry._get_prism_mesh와 같은 Extrusion → 메시). 실패면 null.
        // RhinoCommon 7.0에는 Rhino 8판이 쓰는 Extrusion.Create(평면 인자)·Mesh.CreateFromExtrusion이 없다 — 방향은 PathEnd로 확인하고 Brep을 거쳐 메시화한다.
        // 옆면을 평면 조각으로 나누고(ToBrep(true)) 평면은 경계 정점만 쓰게(SimplePlanes) 해야 뚜껑·옆면 이음매 정점이 맞아 닫힌다
        // (2026-10-29 Rhino 7 실측: ToBrep() + Minimal은 면마다 경계를 따로 쪼개 291동 전부 열림, 정점이 Rhino 8판의 약 10배)
        static readonly MeshingParameters PrismMeshing = new MeshingParameters { SimplePlanes = true };

        static Mesh GetPrismMesh(List<object> parts, double baseZ, double height)
        {
            var result = new Mesh();
            foreach (object part in parts)
            {
                List<object> rings = L(part);
                PolylineCurve outer = GetRingCurve(L(rings[0]), baseZ);
                Extrusion extrusion = Extrusion.Create(outer, height, true);
                if (extrusion != null && extrusion.PathEnd.Z < extrusion.PathStart.Z)   // 커브 평면의 법선이 -Z(시계 방향 링)면 아래로 뽑혔다
                    extrusion = Extrusion.Create(outer, -height, true);
                if (extrusion == null || !extrusion.GetProfileTransformation(0.0).TryGetInverse(out Transform toProfile))
                    continue;
                // 구멍은 세계 좌표가 아니라 단면 좌표로 받는다 — 그대로 넣으면 거절되거나(Z ≠ 0) 엉뚱한 자리에 붙는다
                // (2026-10-30 Rhino 8 실측, 성수 BLD_ID 929230: 그대로 → 부피 206.3 m³·열린 메시, 단면 좌표 → 183.2 m³ = 기대값)
                foreach (object hole in rings.Skip(1))
                {
                    PolylineCurve inner = GetRingCurve(L(hole), baseZ);
                    inner.Transform(toProfile);
                    extrusion.AddInnerProfile(inner);
                }
                foreach (Mesh mesh in Mesh.CreateFromBrep(extrusion.ToBrep(true), PrismMeshing) ?? new Mesh[0])
                    result.Append(mesh);
            }
            if (result.Faces.Count == 0)
                return null;
            result.Vertices.CombineIdentical(true, true);   // Brep 면마다 따로 나온 메시의 이음매 정점을 합친다
            result.Normals.ComputeNormals();
            result.Compact();
            return result;
        }

        // 항목마다: 메시(지형 등) 하나, 각기둥(건물)은 동마다 Mesh 하나, 폴리라인은 줄마다 커브 하나. 출력: 만든 객체 id(실패한 동·항목은 빠진다)
        static object Bake(RhinoDoc doc, Dictionary<string, object> data)
        {
            string lotKey = (string)data["lot_key"];
            double scale = GetUnitScale(doc);
            lastShift = L(data["shift"]).Select(D).ToArray();
            bool moved = Math.Abs(lastShift[0]) > 1e-9 || Math.Abs(lastShift[1]) > 1e-9;
            Transform placement = GetPlacement(lastShift, scale);
            var cache = new Dictionary<string, int>();
            var ids = new List<object>();
            bool redraw = doc.Views.RedrawEnabled;
            doc.Views.RedrawEnabled = false;
            try
            {
                foreach (object entry in L(data["items"]))
                {
                    var item = (Dictionary<string, object>)entry;
                    try
                    {
                        List<object> rgb = L(item["rgb"]);
                        int layer = EnsureLayer(doc, (string)item["layer"], System.Drawing.Color.FromArgb(I(rgb[0]), I(rgb[1]), I(rgb[2])), (bool)item["hidden"], cache);
                        var attrs = (Dictionary<string, object>)item["attrs"];
                        string name = item["name"] as string;
                        var add = new Func<GeometryBase, string, Dictionary<string, object>, Guid>((geometry, objectName, objectAttrs) =>
                            AddObject(doc, geometry, placement, moved, layer, objectName, objectAttrs, lotKey));
                        if (L(item["faces"]).Count > 0)
                        {
                            ids.Add(add(GetMesh(L(item["verts"]), L(item["faces"])), name, attrs));
                        }
                        else if (L(item["prisms"]).Count > 0)
                        {
                            foreach (object entryPrism in L(item["prisms"]))
                            {
                                List<object> prism = L(entryPrism);   // [파트, 바닥 Z, 높이, 속성, 이름]
                                Mesh mesh = GetPrismMesh(L(prism[0]), D(prism[1]), D(prism[2]));
                                if (mesh == null)   // 자기교차 발자국 등 — 건너뛴다
                                    continue;
                                ids.Add(add(mesh, prism[4] as string, (Dictionary<string, object>)prism[3]));
                            }
                        }
                        else
                        {
                            foreach (object entryLine in L(item["polylines"]))
                            {
                                List<object> line = L(entryLine);   // [점, 닫힘]
                                var points = L(line[0]).Select(p => new Point3d(D(L(p)[0]), D(L(p)[1]), D(L(p)[2]))).ToList();
                                if ((bool)line[1] && points.Count > 2)
                                    points.Add(points[0]);
                                if (points.Count >= 2)
                                    ids.Add(add(new PolylineCurve(points), name, attrs));
                            }
                        }
                    }
                    catch (Exception e)
                    {
                        RhinoApp.WriteLine("[Gorani] {0} {1}: {2}", item["layer"], item["name"], e.Message);
                    }
                }
            }
            finally
            {
                doc.Views.RedrawEnabled = redraw;
                doc.Views.Redraw();
            }
            return ids.Where(id => (Guid)id != Guid.Empty).Select(id => id.ToString()).ToList<object>();
        }

        // 원점 표식(CTX::Ref — Point + 'ORIGIN E … N …' TextDot, 속성 = Ref 속성 전부)을 로컬 원점에(context_baker.write_ref_and_origin)
        static object AddRef(RhinoDoc doc, Dictionary<string, object> args)
        {
            double scale = GetUnitScale(doc);
            lastShift = L(args["shift"]).Select(D).ToArray();
            bool moved = Math.Abs(lastShift[0]) > 1e-9 || Math.Abs(lastShift[1]) > 1e-9;
            List<object> rgb = L(args["rgb"]);
            int layer = EnsureLayer(doc, (string)args["layer"], System.Drawing.Color.FromArgb(I(rgb[0]), I(rgb[1]), I(rgb[2])), false, new Dictionary<string, int>());
            var attrs = (Dictionary<string, object>)args["attrs"];
            string lotKey = (string)args["lot_key"];
            Transform placement = GetPlacement(lastShift, scale);
            Guid point = AddObject(doc, new Point(Point3d.Origin), placement, moved, layer, "origin", attrs, lotKey);
            Guid label = AddObject(doc, new TextDot((string)args["label"], Point3d.Origin), placement, moved, layer, "origin_label", attrs, lotKey);
            doc.Views.Redraw();
            return new List<object> { point.ToString(), label.ToString() };
        }

        // 마지막으로 구운 객체를 로컬 좌표(옮기기 전)로 사본 context.3dm에 — 헤드리스 문서에 넣어 쓴다(레이어 경로·색·숨김 그대로). 출력: 객체 수
        static object Save(RhinoDoc doc, string path)
        {
            if (lastIds.Count == 0)
                throw new InvalidOperationException("No objects to save");
            double scale = GetUnitScale(doc);
            Transform back = Transform.Translation(-lastShift[0] * scale, -lastShift[1] * scale, 0.0);
            RhinoDoc copy = RhinoDoc.CreateHeadless(null);
            try
            {
                copy.ModelUnitSystem = doc.ModelUnitSystem;
                var cache = new Dictionary<string, int>();
                int count = 0;
                foreach (Guid id in lastIds)
                {
                    RhinoObject rhinoObject = doc.Objects.FindId(id);
                    if (rhinoObject == null)
                        continue;
                    GeometryBase geometry = rhinoObject.Geometry.Duplicate();
                    geometry.Transform(back);
                    Layer layer = doc.Layers[rhinoObject.Attributes.LayerIndex];
                    ObjectAttributes attributes = rhinoObject.Attributes.Duplicate();
                    attributes.LayerIndex = EnsureLayer(copy, layer.FullPath, layer.Color, !layer.IsVisible, cache);
                    if (copy.Objects.Add(geometry, attributes) != Guid.Empty)
                        count++;
                }
                var options = new FileWriteOptions { SuppressDialogBoxes = true, IncludeRenderMeshes = false, IncludePreviewImage = false };
                if (!copy.WriteFile(path, options))
                    throw new IOException("Could not write " + path);
                return count;
            }
            finally
            {
                copy.Dispose();
            }
        }

        // ── 다시 넣기·줌·커브 ─────────────────────────────────

        // context.3dm(로컬 좌표)을 Import하고 shift(m)만큼 옮겨 이 도구의 객체로 표시한다. 단위는 Import가 문서 단위로 바꾼다
        static object Import(RhinoDoc doc, Dictionary<string, object> args)
        {
            string path = (string)args["path"];
            string lotKey = args["lot_key"] as string ?? "";
            double scale = GetUnitScale(doc);
            lastShift = L(args["shift"]).Select(D).ToArray();
            bool moved = Math.Abs(lastShift[0]) > 1e-9 || Math.Abs(lastShift[1]) > 1e-9;
            var before = new HashSet<Guid>(GetAllObjects(doc).Select(o => o.Id));
            if (!RhinoApp.RunScript("_-Import \"" + path + "\" _Enter", false))
                throw new IOException("Rhino could not import " + path);
            var added = GetAllObjects(doc).Where(o => !before.Contains(o.Id)).ToList();
            lastIds = new List<Guid>();
            Transform placement = Transform.Translation(lastShift[0] * scale, lastShift[1] * scale, 0.0);
            var layers = new HashSet<int>();
            bool redraw = doc.Views.RedrawEnabled;
            doc.Views.RedrawEnabled = false;
            try
            {
                foreach (RhinoObject rhinoObject in added)   // 옮기며(메시는 배정밀도로) 새 객체로 바꿔 넣는다
                {
                    var attrs = rhinoObject.Attributes.GetUserStrings();
                    var values = attrs.AllKeys.ToDictionary(key => key, key => (object)attrs[key]);
                    AddObject(doc, rhinoObject.Geometry.Duplicate(), placement, moved, rhinoObject.Attributes.LayerIndex, rhinoObject.Attributes.Name, values, lotKey);
                    layers.Add(rhinoObject.Attributes.LayerIndex);
                    doc.Objects.Delete(rhinoObject, true, true);
                }
            }
            finally
            {
                doc.Views.RedrawEnabled = redraw;
                doc.Objects.UnselectAll();
                doc.Views.Redraw();
            }
            return new Dictionary<string, object> { { "objects", lastIds.Count }, { "layers", layers.Count } };
        }

        // 대상지(CTX::Site의 이 lot_key 객체) + 대각선 반 여백(한 변 min_span 이상), 없으면 box = [x, y, half](로컬 m)
        static object Zoom(RhinoDoc doc, Dictionary<string, object> args)
        {
            var view = doc.Views.ActiveView;
            if (view == null)
                return false;
            double scale = GetUnitScale(doc);
            string lotKey = args["lot_key"] as string;
            BoundingBox box = BoundingBox.Empty;
            int index = doc.Layers.FindByFullPath(RootLayer + "::Site", -1);
            if (lotKey != null && index >= 0)
                foreach (RhinoObject rhinoObject in doc.Objects.FindByLayer(doc.Layers[index]) ?? new RhinoObject[0])
                    if (rhinoObject.Attributes.GetUserString(LotKey) == lotKey)
                        box.Union(rhinoObject.Geometry.GetBoundingBox(true));
            if (box.IsValid)
            {
                double span = Math.Max(box.Max.X - box.Min.X, box.Max.Y - box.Min.Y);
                double margin = Math.Max(box.Diagonal.Length * 0.5, (D(args["min_span"]) * scale - span) * 0.5);
                box.Inflate(margin, margin, 0.0);
            }
            else if (args["box"] is List<object> center)
            {
                double x = D(center[0]) * scale, y = D(center[1]) * scale, half = D(center[2]) * scale;
                box = new BoundingBox(x - half, y - half, -half, x + half, y + half, half);
            }
            else
            {
                return false;
            }
            view.ActiveViewport.ZoomBoundingBox(box);
            view.Redraw();
            return true;
        }

        // 선택해 둔 닫힌 평면 커브 하나 → 문서 좌표 m 링. 안 되는 까닭은 problem(사이드카가 번역 문구로 바꾼다: open·planar·tilted·self)
        static object PickCurve(RhinoDoc doc, double tolerance)
        {
            var curves = doc.Objects.GetSelectedObjects(false, false).Where(o => o.Geometry is Curve).ToList();
            var result = new Dictionary<string, object> { { "count", curves.Count }, { "ring", null }, { "problem", "" } };
            if (curves.Count != 1)
                return result;
            var curve = (Curve)curves[0].Geometry;
            double scale = GetUnitScale(doc);
            if (!curve.IsClosed)
                result["problem"] = "open";
            else if (!curve.TryGetPlane(out Plane plane, doc.ModelAbsoluteTolerance))
                result["problem"] = "planar";
            else if (Math.Abs(plane.Normal.Z) < 0.999)
                result["problem"] = "tilted";
            else if ((Intersection.CurveSelf(curve, doc.ModelAbsoluteTolerance)?.Count ?? 0) > 0)
                result["problem"] = "self";
            if ((string)result["problem"] != "")
                return result;
            if (!curve.TryGetPolyline(out Polyline polyline))
            {
                PolylineCurve approx = curve.ToPolyline(tolerance * scale, RhinoMath.ToRadians(2.0), 0.0, 0.0);
                if (approx == null || !approx.TryGetPolyline(out polyline))
                {
                    result["problem"] = "planar";
                    return result;
                }
            }
            result["ring"] = polyline.Take(polyline.Count - 1).Select(p => (object)new List<object> { p.X / scale, p.Y / scale, p.Z / scale }).ToList();
            return result;
        }

        // ── JSON 값 꺼내기 ────────────────────────────────────

        static List<object> L(object value) => value as List<object> ?? new List<object>();
        static double D(object value) => Convert.ToDouble(value, CultureInfo.InvariantCulture);
        static int I(object value) => (int)Math.Round(D(value));
    }

    // 사이드카와 주고받는 JSON — net48·Mono(Rhino 7 Mac) 공통으로 쓸 표준 라이브러리가 없어 직접 읽고 쓴다.
    // 읽기: 객체 → Dictionary<string, object>, 배열 → List<object>, 수 → double. 쓰기: 비ASCII는 \u 이스케이프(파이프 인코딩과 무관하게)
    static class Json
    {
        public static object Parse(string text)
        {
            int i = 0;
            return ReadValue(text, ref i);
        }

        static void SkipSpace(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i]))
                i++;
        }

        static object ReadValue(string s, ref int i)
        {
            SkipSpace(s, ref i);
            char c = s[i];
            if (c == '{')
            {
                i++;
                var dict = new Dictionary<string, object>();
                SkipSpace(s, ref i);
                if (s[i] == '}') { i++; return dict; }
                while (true)
                {
                    SkipSpace(s, ref i);
                    string key = ReadString(s, ref i);
                    SkipSpace(s, ref i);
                    i++;   // :
                    dict[key] = ReadValue(s, ref i);
                    SkipSpace(s, ref i);
                    if (s[i++] == '}') return dict;
                }
            }
            if (c == '[')
            {
                i++;
                var list = new List<object>();
                SkipSpace(s, ref i);
                if (s[i] == ']') { i++; return list; }
                while (true)
                {
                    list.Add(ReadValue(s, ref i));
                    SkipSpace(s, ref i);
                    if (s[i++] == ']') return list;
                }
            }
            if (c == '"')
                return ReadString(s, ref i);
            foreach (var word in new[] { "true", "false", "null" })
                if (string.CompareOrdinal(s, i, word, 0, word.Length) == 0)
                {
                    i += word.Length;
                    return word == "null" ? null : (object)(word == "true");
                }
            int start = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0)
                i++;
            if (i == start)
                throw new FormatException("Bad JSON at " + start);
            return double.Parse(s.Substring(start, i - start), CultureInfo.InvariantCulture);
        }

        static string ReadString(string s, ref int i)
        {
            i++;   // "
            var builder = new StringBuilder();
            while (true)
            {
                char c = s[i++];
                if (c == '"')
                    return builder.ToString();
                if (c != '\\')
                {
                    builder.Append(c);
                    continue;
                }
                char e = s[i++];
                switch (e)
                {
                    case 'n': builder.Append('\n'); break;
                    case 'r': builder.Append('\r'); break;
                    case 't': builder.Append('\t'); break;
                    case 'b': builder.Append('\b'); break;
                    case 'f': builder.Append('\f'); break;
                    case 'u': builder.Append((char)Convert.ToInt32(s.Substring(i, 4), 16)); i += 4; break;
                    default: builder.Append(e); break;
                }
            }
        }

        public static string Write(object value)
        {
            var builder = new StringBuilder();
            WriteValue(builder, value);
            return builder.ToString();
        }

        static void WriteValue(StringBuilder b, object value)
        {
            switch (value)
            {
                case null: b.Append("null"); break;
                case string s: WriteString(b, s); break;
                case bool t: b.Append(t ? "true" : "false"); break;
                case double _:
                case float _:
                case int _:
                case long _:
                    b.Append(Convert.ToDouble(value).ToString("R", CultureInfo.InvariantCulture)); break;
                case IDictionary<string, object> dict:
                    b.Append('{');
                    bool first = true;
                    foreach (var pair in dict)
                    {
                        if (!first) b.Append(',');
                        first = false;
                        WriteString(b, pair.Key);
                        b.Append(':');
                        WriteValue(b, pair.Value);
                    }
                    b.Append('}');
                    break;
                case IEnumerable list:
                    b.Append('[');
                    bool head = true;
                    foreach (object item in list)
                    {
                        if (!head) b.Append(',');
                        head = false;
                        WriteValue(b, item);
                    }
                    b.Append(']');
                    break;
                default: WriteString(b, Convert.ToString(value, CultureInfo.InvariantCulture)); break;
            }
        }

        static void WriteString(StringBuilder b, string s)
        {
            b.Append('"');
            foreach (char c in s)
            {
                if (c == '"' || c == '\\')
                    b.Append('\\').Append(c);
                else if (c < 0x20 || c > 0x7e)
                    b.Append("\\u").Append(((int)c).ToString("x4"));
                else
                    b.Append(c);
            }
            b.Append('"');
        }
    }
}
