using Godot;
using System.Collections.Generic;

public partial class EventLogPanel : PanelContainer
{
    private readonly RichTextLabel _log = new();

    public override void _Ready()
    {
        Name = "EventLogPanel";
        CustomMinimumSize = new Vector2(650, 180);
        Position = new Vector2(10, 530);
        AddThemeStyleboxOverride("panel", new StyleBoxFlat { BgColor = new Color("0a1a2b"), BorderColor = new Color("35e6a5"), BorderWidthLeft = 2, BorderWidthTop = 2, BorderWidthRight = 2, BorderWidthBottom = 2 });

        _log.BbcodeEnabled = false;
        _log.ScrollActive = true;
        _log.FitContent = true;
        _log.SizeFlagsHorizontal = SizeFlags.ExpandFill;
        _log.SizeFlagsVertical = SizeFlags.ExpandFill;
        AddChild(_log);
    }

    public void UpdateLog(IReadOnlyList<string> entries)
    {
        _log.Clear();
        for (int i = entries.Count - 1; i >= 0; i--)
        {
            _log.AddText(entries[i] + "\n");
        }
    }
}
