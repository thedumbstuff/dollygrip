# Offline voiceover for examples/counting_cards.py using Windows' built-in TTS.
# Usage: powershell -File examples/counting_voice.ps1 -OutDir D:\counting\voice
param([string]$OutDir = "D:\counting\voice")
New-Item -ItemType Directory -Force $OutDir | Out-Null
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$zira = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name } | Where-Object { $_ -like '*Zira*' } | Select-Object -First 1
if ($zira) { $s.SelectVoice($zira) }
$s.Rate = -2
$lines = [ordered]@{
  "00_intro" = "Let's count together, from one to ten!"
  "01" = "One."; "02" = "Two."; "03" = "Three."; "04" = "Four."; "05" = "Five."
  "06" = "Six."; "07" = "Seven."; "08" = "Eight."; "09" = "Nine."; "10" = "Ten!"
  "11_outro" = "Great job! You counted all the way to ten."
}
foreach ($k in $lines.Keys) { $s.SetOutputToWaveFile("$OutDir\voice_$k.wav"); $s.Speak($lines[$k]) }
$s.SetOutputToNull(); $s.Dispose()
Get-ChildItem "$OutDir\*.wav" | ForEach-Object { $_.Name }
