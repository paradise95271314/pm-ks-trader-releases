#define MyAppName "PM-KS交易桌面"
#define MyAppVersion "1.3.3"
#define MyAppExeName "PM-KS交易桌面.exe"

[Setup]
AppId={{746581B4-4D73-4BE5-B6D6-78A4019038C0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\PM-KS Trader
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=PM-KS-Trader-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Files]
Source: "dist\PM-KS交易桌面\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
