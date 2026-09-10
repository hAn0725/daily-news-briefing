' ============================================================
' 每日新闻简报 - 计划任务隐藏启动器
' 由 Windows 计划任务调用：以完全隐藏的窗口运行 run_daily.bat，
' 避免"等待联网重试"期间整天挂着黑色控制台窗口。
' ============================================================
Option Explicit
Const ForAppending = 8
Dim fso, dirPath, sh, logPath, command, exitCode, errorNumber, errorText
Dim targetBat, re
Set fso = CreateObject("Scripting.FileSystemObject")
dirPath = fso.GetParentFolderName(WScript.ScriptFullName)
If Not fso.FolderExists(dirPath & "\logs") Then
    fso.CreateFolder dirPath & "\logs"
End If
logPath = dirPath & "\logs\scheduler.log"
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dirPath

Sub WriteLog(message)
    Dim stream
    On Error Resume Next
    Set stream = fso.OpenTextFile(logPath, ForAppending, True)
    If Err.Number = 0 Then
        stream.WriteLine Now & " " & message
        stream.Close
    End If
    Err.Clear
    On Error GoTo 0
End Sub

' Optional arg: which bat to launch. Default run_daily.bat.
' The watchdog task passes run_watchdog.bat. Only plain file names
' (letters/digits/underscore/hyphen + .bat) are accepted, no paths.
targetBat = "run_daily.bat"
If WScript.Arguments.Count >= 1 Then
    Set re = New RegExp
    re.Pattern = "^[A-Za-z0-9_\-]+\.bat$"
    re.IgnoreCase = True
    If re.Test(WScript.Arguments(0)) Then
        targetBat = WScript.Arguments(0)
    Else
        WriteLog "BAD_TARGET arg=" & WScript.Arguments(0)
        WScript.Quit 101
    End If
End If

' Wait synchronously and report the real exit code.
command = """" & dirPath & "\" & targetBat & """"
WriteLog "START command=" & command
On Error Resume Next
exitCode = sh.Run(command, 0, True)
errorNumber = Err.Number
errorText = Err.Description
Err.Clear
On Error GoTo 0

If errorNumber <> 0 Then
    WriteLog "LAUNCH_ERROR code=" & errorNumber & " message=" & errorText
    WScript.Quit 100
End If

WriteLog "END exit_code=" & exitCode
WScript.Quit exitCode
