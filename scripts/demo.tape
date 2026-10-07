# Demo GIF for the README. Run with: vhs scripts/demo.tape
# Needs the fake server: python scripts/fake_server.py

Output docs/img/demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 1000
Set Height 560
Set Padding 14
Set BorderRadius 8
Set WindowBar Colorful
Set WindowBarSize 34
Set CursorBlink false
Set TypingSpeed 45ms
Set Framerate 30
Set PlaybackSpeed 1.6
Set Theme "tokyonight"
Env LLMTAP_CONFIG "tests/local.toml"
Env LLMTAP_LANG "en"

Type "llmtap list"
Enter
Sleep 1.6s
Type "clear"
Enter

Type "llmtap test local7b"
Enter
Sleep 2.6s
Type "clear"
Enter

Type "llmtap bench local7b -n 4 -c 2"
Enter
Sleep 4s
Type "clear"
Enter

Type "llmtap scan local7b"
Enter
Sleep 3.4s
Type "clear"
Enter

Type "llmtap probe local7b"
Enter
Sleep 8s
