# Zeigt eine Windows-Benachrichtigung an.
#
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File meldung.ps1 `
#       -Titel "Lieferwaechter" -Text "..." [-Ton]
#
# Zwei Wege, weil der erste nicht ueberall verfuegbar ist: Die Toast-Api
# gibt es nur auf Windows 10 und neuer und nur in einer Desktopsitzung.
# Schlaegt sie fehl, bleibt die alte Sprechblase im Infobereich.
param(
  [string]$Titel = "Lieferwaechter",
  [string]$Text  = "",
  [switch]$Ton
)

function Zeige-Toast {
  param($Titel, $Text)
  [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
  [void][Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime]
  [void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime]

  # Eine Toast-Meldung braucht eine angemeldete Anwendung. Die Kennung von
  # Windows PowerShell ist immer vorhanden - eine eigene muesste erst im
  # Startmenue eingetragen werden.
  $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'

  $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
           [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  $knoten = $xml.GetElementsByTagName('text')
  [void]$knoten.Item(0).AppendChild($xml.CreateTextNode($Titel))
  [void]$knoten.Item(1).AppendChild($xml.CreateTextNode($Text))
  $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
}

function Zeige-Sprechblase {
  param($Titel, $Text)
  Add-Type -AssemblyName System.Windows.Forms
  $symbol = New-Object System.Windows.Forms.NotifyIcon
  $symbol.Icon = [System.Drawing.SystemIcons]::Information
  $symbol.BalloonTipTitle = $Titel
  $symbol.BalloonTipText  = $Text
  $symbol.Visible = $true
  $symbol.ShowBalloonTip(15000)
  # Ohne Wartezeit verschwindet die Sprechblase mit dem Prozess, der sie
  # zeigt - man saehe sie nie.
  Start-Sleep -Seconds 12
  $symbol.Dispose()
}

try {
  Zeige-Toast -Titel $Titel -Text $Text
  Write-Output "toast"
} catch {
  try {
    Zeige-Sprechblase -Titel $Titel -Text $Text
    Write-Output "sprechblase"
  } catch {
    Write-Output ("fehlgeschlagen: " + $_.Exception.Message)
    exit 1
  }
}

if ($Ton) { [console]::beep(880, 250); [console]::beep(660, 350) }
