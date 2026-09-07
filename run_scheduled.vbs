' ============================================================
' 每日新闻简报 - 计划任务隐藏启动器
' 由 Windows 计划任务调用：以完全隐藏的窗口运行 run_daily.bat，
' 避免"等待联网重试"期间整天挂着黑色控制台窗口。
' ============================================================
Option Explicit
Const ForAppending = 8
Dim fso, dirPath, sh, logPath, command, exitCode, errorNumber, errorText
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

' 同步等待并回传真实退出码，避免只记录 wscript 启动成功。
command = """" & dirPath & "\run_daily.bat"""
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
