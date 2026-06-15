# Development

## Live Extension Link

For day-to-day development, use a Blender user extension link instead of repeatedly installing a packaged zip.

The source extension lives at:

```text
addon/claude_blender
```

Run this from the repository root:

```powershell
.\scripts\link_blender_dev_extension.ps1
```

By default the script targets Blender 5.1's user extension repository:

```text
%APPDATA%\Blender Foundation\Blender\5.1\extensions\user_default\claude_blender
```

If an installed copy already exists, the script moves it into `.dev-link-backups` beside the user extension repository and creates a Windows junction back to this checkout. After that, edit files in `addon/claude_blender` and restart Blender to load the changes.

Disabling and re-enabling the extension may also work for small edits because `__init__.py` reloads the extension submodules during registration. Restarting Blender is safer after edits to registered Blender classes, properties, panels, operators, or module import order.

With the link active, you do not need to reinstall the zip for normal local testing. Rebuild and reinstall the zip only when testing clean install/load behavior, release packaging, or a user's packaged-extension path. After bridge or MCP server changes, use `Copy MCP Config` again and refresh or restart the MCP client because many clients cache tool lists and server configs.

To target a different Blender version:

```powershell
.\scripts\link_blender_dev_extension.ps1 -BlenderVersion 5.2
```

To target a custom extension repository:

```powershell
.\scripts\link_blender_dev_extension.ps1 -ExtensionRepo "C:\path\to\extensions\user_default"
```
