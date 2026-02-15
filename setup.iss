; File is UTF-8.

#define MyAppName "CyberDeck"
#define MyAppVersion "1.3.0"
#define MyAppPublisher "Overl1te"
#define MyAppURL "https://github.com/Overl1te/CyberDeck"
#define MyAppExeName "CyberDeck.exe"
#define MyAppId "{{9570AD34-C0B3-4CCE-B105-DF8EBF877DB2}"

; Project root = folder where this .iss is located
#define ProjectDir SourcePath

; Build output folder (Nuitka --standalone)
#define DistDir ProjectDir + "dist\\"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage

; Installer look & feel
WizardStyle=modern
SetupIconFile={#ProjectDir}icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; We install into Program Files and (optionally) add firewall rules.
PrivilegesRequired=admin

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

SolidCompression=yes
Compression=lzma2

OutputDir={#ProjectDir}Output
OutputBaseFilename=CyberDeck_Setup_v{#MyAppVersion}

; Texts shown in wizard
LicenseFile={#ProjectDir}TERMS_OF_USE.txt

VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.TaskExtraGroup=Дополнительно
english.TaskExtraGroup=Extra
russian.TaskAutostart=Запускать вместе с Windows (текущий пользователь)
english.TaskAutostart=Start with Windows (current user)
russian.TaskFirewall=Добавить правила в Брандмауэр Windows (TCP 8080, UDP 5555)
english.TaskFirewall=Add Windows Firewall rules (TCP 8080, UDP 5555)
russian.StatusFirewallTCP=Настройка брандмауэра (TCP 8080)...
english.StatusFirewallTCP=Configuring firewall (TCP 8080)...
russian.StatusFirewallUDP=Настройка брандмауэра (UDP 5555)...
english.StatusFirewallUDP=Configuring firewall (UDP 5555)...

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart"; Description: "{cm:TaskAutostart}"; GroupDescription: "{cm:TaskExtraGroup}"; Flags: unchecked
Name: "firewall"; Description: "{cm:TaskFirewall}"; GroupDescription: "{cm:TaskExtraGroup}"; Flags: checkedonce

[Files]
; Nuitka Windows build layout:
;   dist\launcher.dist\*
; Optional fallback for renamed dist folder:
;   dist\CyberDeck.dist\*
; Optional flat layout:
;   dist\CyberDeck.exe
Source: "{#DistDir}launcher.dist\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#DistDir}CyberDeck.dist\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#DistDir}CyberDeck.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\\{#MyAppName}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"
Name: "{autoprograms}\\{#MyAppName}\\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Optional autostart via HKCU Run (no admin needed at runtime)
Root: HKCU; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Run"; ValueType: string; ValueName: "CyberDeck"; ValueData: """{app}\\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
; Firewall rules (optional)
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""CyberDeck TCP"""; Flags: runhidden; Tasks: firewall
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""CyberDeck UDP"""; Flags: runhidden; Tasks: firewall
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""CyberDeck TCP"" dir=in action=allow protocol=TCP localport=8080 profile=any"; Flags: runhidden; Tasks: firewall; StatusMsg: "{cm:StatusFirewallTCP}"
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""CyberDeck UDP"" dir=in action=allow protocol=UDP localport=5555 profile=any"; Flags: runhidden; Tasks: firewall; StatusMsg: "{cm:StatusFirewallUDP}"

; Launch after install (UAC-aware for binaries built with --windows-uac-admin)
Filename: "{app}\\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent shellexec; Verb: "runas"

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""CyberDeck TCP"""; Flags: runhidden
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""CyberDeck UDP"""; Flags: runhidden
