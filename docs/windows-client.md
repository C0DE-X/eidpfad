# Windows-11-Client

## Entwicklungsstart

Godot 4 oeffnen, `client/project.godot` importieren und die Hauptszene starten.
Fuer lokale Tests wird `http://127.0.0.1:8080` als Server verwendet. Fuer einen
VPS muss eine HTTPS-Domain mit gueltigem Zertifikat eingetragen werden; der
Client leitet sie automatisch auf WSS fuer Kampagnenverbindungen ab.

## Export

In Godot unter `Editor > Manage Export Templates` die zur Editorversion
passenden Templates installieren. Danach in PowerShell:

```powershell
.\client\build-windows.ps1 -Godot "C:\Tools\Godot\godot.exe"
```

Der Preset `Windows 11` erzeugt eine x86_64-EXE mit eingebettetem PCK und packt
sie in `dist/client/eidpfad-windows-x86_64.zip`.

## Lokale Daten

Godot speichert `eidpfad-client.cfg` unter `user://`. Enthalten sind:

- letzte Serveradresse
- Profil-ID und Anzeigename
- Geraete-Token
- letzte Kampagnen-ID und Einladungscode

Die Datei gehoert zum Windows-Benutzerprofil und darf nicht mit anderen
Benutzern geteilt werden. Fuer einen oeffentlichen Release sollte das
Geraete-Token spaeter durch kurzlebige Zugriffstoken mit sicherem Refresh-Token
im Windows Credential Manager ersetzt werden.

## Distribution

Windows SmartScreen kann bei unsignierten EXE-Dateien warnen. Fuer eine
oeffentliche Verteilung sollte die finale EXE nach dem Export mit einem
Code-Signing-Zertifikat signiert werden. Signierung ist absichtlich nicht mit
einem privaten Schluessel im Repository vorkonfiguriert.
