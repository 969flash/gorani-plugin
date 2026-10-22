#include "APIEnvir.h"
#include "ACAPinc.h"

#include "DGModule.hpp"
#include "Process.hpp"

#include "GoraniLauncher.hpp"
#include "ResourceIds.hpp"

static Int32 archicadVersion = 0;
static GS::Array<GS::Process> launched;   // 띄운 사이드카 손잡이 — 놓아도 프로세스는 돈다. 메뉴를 누른 수만큼만 쌓인다

void SetGoraniArchicadVersion (Int32 mainVersion)
{
    archicadVersion = mainVersion;
}

static GS::UniString GetString (Int32 index)
{
    return RSGetIndString (ID_GORANI_STRINGS, index, ACAPI_GetOwnResModule ());
}

// Gorani 폴더 = scripts/cmd_archicad.py가 있는 곳. 애드온이 든 폴더, 없으면 그 위 폴더(버전별 하위 폴더 배치)
static bool FindGoraniFolder (IO::Location& folder)
{
    IO::Location location;
    ACAPI_GetOwnLocation (&location);   // .bundle(맥) 또는 .apx(윈도)
    for (int up = 0; up < 2; ++up) {
        location.DeleteLastLocalName ();
        IO::Location script = location;
        script.AppendToLocal (IO::Name ("scripts"));
        script.AppendToLocal (IO::Name ("cmd_archicad.py"));
        if (IO::fileSystem.Contains (script)) {
            folder = location;
            return true;
        }
    }
    return false;
}

static IO::Location GetPythonLocation (const IO::Location& folder)
{
    IO::Location python = folder;
    python.AppendToLocal (IO::Name ("python"));
#if defined (WINDOWS)
    python.AppendToLocal (IO::Name ("win-x64"));
    python.AppendToLocal (IO::Name ("python.exe"));
#else
#if defined (__arm64__) || defined (__aarch64__)
    python.AppendToLocal (IO::Name ("mac-arm64"));
#else
    python.AppendToLocal (IO::Name ("mac-x64"));
#endif
    python.AppendToLocal (IO::Name ("bin"));
    python.AppendToLocal (IO::Name ("python3.12"));
#endif
    return python;
}

void LaunchGorani ()
{
    IO::Location folder;
    if (!FindGoraniFolder (folder)) {
        DGAlert (DG_ERROR, GetString (ID_GORANI_STRINGS_ERROR_TITLE), GetString (ID_GORANI_STRINGS_MISSING), GS::EmptyUniString, "OK");
        return;
    }
    IO::Location python = GetPythonLocation (folder);
    IO::Location script = folder;
    script.AppendToLocal (IO::Name ("scripts"));
    script.AppendToLocal (IO::Name ("cmd_archicad.py"));
    if (!IO::fileSystem.Contains (python)) {
        DGAlert (DG_ERROR, GetString (ID_GORANI_STRINGS_ERROR_TITLE), GetString (ID_GORANI_STRINGS_MISSING), GS::EmptyUniString, "OK");
        return;
    }

    UShort port = 0;
    ACAPI_Command_GetHttpConnectionPort (&port);
    GS::UniString pythonPath;
    GS::UniString scriptPath;
    python.ToPath (&pythonPath);
    script.ToPath (&scriptPath);
    // -I: 사용자 환경(PYTHONPATH 등) 무시, -B: 애드온 폴더에 __pycache__를 쓰지 않는다, -X utf8: 경로·로그 UTF-8
    const GS::Array<GS::UniString> argv = {
        "-I", "-B", "-X", "utf8", scriptPath,
        "--port", GS::ValueToUniString (port),
        "--version", GS::ValueToUniString (archicadVersion)
    };
    try {
        GS::Process process = GS::Process::Create (pythonPath, argv, GS::Process::CreateNoWindow);
        if (process.IsValid ()) {
            launched.Push (process);
            return;
        }
    } catch (...) {
    }
    DGAlert (DG_ERROR, GetString (ID_GORANI_STRINGS_ERROR_TITLE), GetString (ID_GORANI_STRINGS_START_FAILED), pythonPath, "OK");
}
