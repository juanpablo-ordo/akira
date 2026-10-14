Option Explicit
Dim shell, fs, directory, command
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
directory = fs.GetParentFolderName(WScript.ScriptFullName)
command = "powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & directory & "\AKIRA_Instalador.ps1"""
shell.Run command, 0, False
