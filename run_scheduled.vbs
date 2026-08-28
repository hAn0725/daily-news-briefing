' ============================================================
' 每日新闻简报 - 计划任务隐藏启动器
' 由 Windows 计划任务调用：以完全隐藏的窗口运行 run_daily.bat，
' 避免"等待联网重试"期间整天挂着黑色控制台窗口。
' ============================================================
Option Explicit
Dim fso, dirPath, sh
Set fso = CreateObject("Scripting.FileSystemObject")
dirPath = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dirPath
sh.Run """" & dirPath & "\run_daily.bat""", 0, False
