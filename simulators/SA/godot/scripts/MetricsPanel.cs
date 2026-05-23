using Godot;
using System;
using System.Collections.Generic;

public partial class MetricsPanel : PanelContainer
{
    private readonly Label _label = new();

    public override void _Ready()
    {
        Name = "MetricsPanel";
        CustomMinimumSize = new Vector2(360, 180);
        Position = new Vector2(910, 10);
        AddThemeStyleboxOverride("panel", new StyleBoxFlat { BgColor = new Color("0a1a2b"), BorderColor = new Color("2cb8ff"), BorderWidthLeft = 2, BorderWidthTop = 2, BorderWidthRight = 2, BorderWidthBottom = 2 });

        _label.AutowrapMode = TextServer.AutowrapMode.Word;
        _label.HorizontalAlignment = HorizontalAlignment.Left;
        _label.VerticalAlignment = VerticalAlignment.Top;
        _label.SizeFlagsHorizontal = SizeFlags.ExpandFill;
        _label.SizeFlagsVertical = SizeFlags.ExpandFill;
        AddChild(_label);
    }

    public void UpdateMetrics(double simTime, int generated, int queued, int delivered, int expired, double avgLatency, List<AircraftAgent> aircraft)
    {
        int busyCount = 0;
        foreach (var a in aircraft)
        {
            if (a.State != AircraftState.Idle)
            {
                busyCount++;
            }
        }

        var util = aircraft.Count == 0 ? 0 : 100.0 * busyCount / aircraft.Count;
        _label.Text =
            "AIRFREIGHT LOGISTICS SIM\n" +
            $"Simulation Time: {simTime,6:0.0}s\n" +
            $"Generated: {generated}\n" +
            $"Queued: {queued}\n" +
            $"Delivered: {delivered}\n" +
            $"Expired: {expired}\n" +
            $"Avg Latency: {avgLatency:0.0}s\n" +
            $"Aircraft Utilization: {util:0}%";
    }
}
