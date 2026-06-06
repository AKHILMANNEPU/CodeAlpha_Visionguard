[Setup]
AppName=Visionguard
AppVersion=1.0
AppPublisher=Visionguard AI
DefaultDirName={autopf}\Visionguard
DefaultGroupName=Visionguard
OutputDir=Output
OutputBaseFilename=Visionguard_Setup
SetupIconFile=assets\icon.ico
WizardImageFile=assets\wizard.bmp
WizardSmallImageFile=assets\wizard_small.bmp
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\VisionGuard_AI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Visionguard"; Filename: "{app}\VisionGuard_AI.exe"; IconFilename: "{app}\VisionGuard_AI.exe"
Name: "{autodesktop}\Visionguard"; Filename: "{app}\VisionGuard_AI.exe"; Tasks: desktopicon; IconFilename: "{app}\VisionGuard_AI.exe"

[Run]
Filename: "{app}\VisionGuard_AI.exe"; Description: "{cm:LaunchProgram,Visionguard}"; Flags: nowait postinstall skipifsilent
