; inst_dist.nsi
;
; This script is based on example1.nsi but it remembers the directory, 
; has uninstall support and (optionally) installs start menu shortcuts.
;
; It will install inst_dist.nsi into a directory that the user selects.
;
; See install-shared.nsi for a more robust way of checking for administrator rights.
; See install-per-user.nsi for a file association example.

;--------------------------------
;Include Modern UI

!include "MUI2.nsh"
!include "LogicLib.nsh"

;--------------------------------

!ifndef VERSION
  !define VERSION "0.0.0" ; Default value if not provided via CLI
!endif

; The name of the installer
Name "TouCAN-Plot ${VERSION}"

; The file to write
OutFile "toucan-plot-${VERSION}.exe"

; Request application privileges for Windows Vista and higher
RequestExecutionLevel admin

; Build Unicode installer
Unicode True

; The default installation directory
InstallDir $PROGRAMFILES\TouCAN-Plot

; Registry key to check for directory (so if you install again, it will 
; overwrite the old one automatically)
InstallDirRegKey HKLM "Software\NSIS_TouCAN-Plot" "Install_Dir"

;--------------------------------

; Pages

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------

; The stuff to install
Section "TouCAN-Plot (required)"

  SectionIn RO
  
  ; Set output path to the installation directory.
  SetOutPath "$INSTDIR"

  ; Remove cache dir
  RMDir /r "$PROFILE\.toucan-plot"
  
  ; Put file there
  SetOutPath "$INSTDIR"
  File /r "..\toucan-plot.dist\**"

  SetOutPath "$INSTDIR"
  
  ; Write the installation path into the registry
  WriteRegStr HKLM SOFTWARE\NSIS_TouCAN-Plot "Install_Dir" "$INSTDIR"
  
  ; Write the uninstall keys for Windows
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TouCAN-Plot" "DisplayName" "TouCAN-Plot"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TouCAN-Plot" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TouCAN-Plot" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TouCAN-Plot" "NoRepair" 1
  WriteUninstaller "$INSTDIR\uninstall.exe"

  FileOpen $2 "$INSTDIR\install.log" w
SectionEnd

; Optional section (can be disabled by the user)
Section "Start Menu Shortcuts"

  CreateDirectory "$SMPROGRAMS\TouCAN-Plot"
  CreateShortcut "$SMPROGRAMS\TouCAN-Plot\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\TouCAN-Plot\TouCAN-Plot.lnk" "$INSTDIR\TouCAN-Plot.exe"

SectionEnd

;--------------------------------

; Uninstaller

Section "Uninstall"
  
  ; Remove registry keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TouCAN-Plot"
  DeleteRegKey HKLM SOFTWARE\NSIS_TouCAN-Plot

  ; Remove files and uninstaller
  Delete "$INSTDIR\uninstall.exe"

  ; Remove shortcuts, if any
  Delete "$SMPROGRAMS\TouCAN-Plot\*.lnk"

  ; Remove directories
  RMDir /r "$SMPROGRAMS\TouCAN-Plot"
  RMDir /r "$INSTDIR"

SectionEnd
