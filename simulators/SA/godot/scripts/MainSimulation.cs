using Godot;
using System;
using System.Collections.Generic;
using System.Linq;

public partial class MainSimulation : Node2D
{
    private readonly SimulationConfig _config = new();
    private readonly SimulationClock _clock = new();
    private readonly LoadingQueue _queue = new();
    private readonly FleetCoordinator _coordinator = new();

    private PalletSource _source = null!;
    private readonly List<AircraftAgent> _aircraft = new();
    private readonly List<string> _events = new();
    private readonly List<double> _latencies = new();
    private readonly List<string> _deliveredList = new();

    private MetricsPanel _metricsPanel = null!;
    private EventLogPanel _eventLogPanel = null!;
    private bool _simFinished;

    private int _generated;
    private int _expired;
    private int _delivered;

    private readonly Vector2 _originPos = new(230, 300);
    private readonly Vector2 _destinationPos = new(1040, 300);

    public override void _Ready()
    {
        _clock.TimeScale = _config.TimeScale;
        _source = new PalletSource(_config.PalletIntervalSec);

        for (int i = 0; i < _config.AircraftCount; i++)
        {
            var craft = new AircraftAgent($"Aircraft-{i + 1}", _config, _originPos + new Vector2(0, i * 32));
            _aircraft.Add(craft);
        }

        var canvasLayer = new CanvasLayer();
        AddChild(canvasLayer);

        _metricsPanel = new MetricsPanel();
        canvasLayer.AddChild(_metricsPanel);

        _eventLogPanel = new EventLogPanel();
        canvasLayer.AddChild(_eventLogPanel);

        AppendEvent("Simulation started.");
    }

    public override void _Process(double delta)
    {
        if (_simFinished)
        {
            return;
        }

        _clock.Advance(delta);
        var now = _clock.SimTimeSec;

        if (now <= _config.TotalDurationSec)
        {
            _source.Update(now, _config.PalletExpirationSec, pallet =>
            {
                _queue.Enqueue(pallet);
                _generated++;
                AppendEvent($"pallet_generated: {pallet.Id} deadline={pallet.DeadlineTime:0.0}s");
            });
        }

        _queue.ExpireDue(now, pallet =>
        {
            _expired++;
            AppendEvent($"pallet_expired: {pallet.Id}");
        });

        _coordinator.AssignAvailable(_queue, _aircraft, now, _originPos, _destinationPos, AppendEvent);

        foreach (var craft in _aircraft)
        {
            craft.Update(now, (pallet, deliveryTime) =>
            {
                _delivered++;
                _latencies.Add(deliveryTime - pallet.GenerationTime);
                _deliveredList.Insert(0, $"{pallet.Id} @ {deliveryTime:0.0}s");
                if (_deliveredList.Count > 8)
                {
                    _deliveredList.RemoveAt(_deliveredList.Count - 1);
                }
                AppendEvent($"delivery_completed: {pallet.Id} latency={deliveryTime - pallet.GenerationTime:0.0}s");
            }, AppendEvent);
        }

        _metricsPanel.UpdateMetrics(
            now,
            _generated,
            _queue.Count,
            _delivered,
            _expired,
            _latencies.Count == 0 ? 0 : _latencies.Average(),
            _aircraft);
        _eventLogPanel.UpdateLog(_events);

        if (now >= _config.TotalDurationSec)
        {
            _simFinished = true;
            AppendEvent($"Simulation finished at t={now:0.0}s");
            _eventLogPanel.UpdateLog(_events);
        }

        QueueRedraw();
    }

    public override void _Draw()
    {
        DrawRect(new Rect2(0, 0, 1280, 720), new Color("071321"), true);

        DrawRect(new Rect2(0, 0, 420, 520), new Color("10273e"), true);
        DrawRect(new Rect2(420, 0, 440, 520), new Color("0f3450"), true);
        DrawRect(new Rect2(860, 0, 420, 520), new Color("10273e"), true);

        DrawString(ThemeDB.FallbackFont, new Vector2(14, 28), "AIRFREIGHT LOGISTICS SIMULATION", HorizontalAlignment.Left, -1, 28, new Color("9be7ff"));
        DrawString(ThemeDB.FallbackFont, new Vector2(20, 68), "1 ORIGIN AIRPORT / LOADING FACILITY", HorizontalAlignment.Left, -1, 16, Colors.White);
        DrawString(ThemeDB.FallbackFont, new Vector2(460, 68), "4 AIR ROUTE (IN TRANSIT)", HorizontalAlignment.Left, -1, 16, Colors.White);
        DrawString(ThemeDB.FallbackFont, new Vector2(885, 68), "5 DESTINATION AIRPORT / RECEIVING HUB", HorizontalAlignment.Left, -1, 16, Colors.White);

        DrawAirportBlock(_originPos, "Cargo Facility", new Color("2f5575"));
        DrawAirportBlock(_destinationPos, "Receiving Hub", new Color("2f5575"));

        DrawDashedRoute(_originPos + new Vector2(60, 0), _destinationPos + new Vector2(-60, 0), 28, new Color("72d9ff"));
        DrawArrow(_originPos + new Vector2(90, -16), _destinationPos + new Vector2(-90, -16), new Color("7cf59a"));
        DrawArrow(_destinationPos + new Vector2(-90, 16), _originPos + new Vector2(90, 16), new Color("7ca8f5"));
        DrawString(ThemeDB.FallbackFont, new Vector2(570, 315), "OUTBOUND FLIGHT 30s", HorizontalAlignment.Left, -1, 14, new Color("7cf59a"));
        DrawString(ThemeDB.FallbackFont, new Vector2(570, 340), "RETURN FLIGHT 30s", HorizontalAlignment.Left, -1, 14, new Color("7ca8f5"));

        DrawQueuePanel();
        DrawAircraft();
        DrawDeliveredPanel();
    }

    private void DrawQueuePanel()
    {
        DrawRect(new Rect2(20, 95, 350, 390), new Color("0b1a2a"), true);
        DrawString(ThemeDB.FallbackFont, new Vector2(34, 120), $"Loading Queue (FIFO)  count={_queue.Count}", HorizontalAlignment.Left, -1, 14, Colors.LightGoldenrodYellow);

        var items = _queue.Items.Take(10).ToList();
        for (int i = 0; i < items.Count; i++)
        {
            var y = 145 + i * 30;
            var p = items[i];
            var remain = p.DeadlineTime - _clock.SimTimeSec;
            var color = remain > 10 ? new Color("2f6fa0") : remain > 5 ? new Color("b98e2d") : new Color("bf3f38");
            DrawRect(new Rect2(30, y, 330, 24), color, true);
            DrawString(ThemeDB.FallbackFont, new Vector2(38, y + 17), $"{p.Id}   deadline in {Math.Max(0, remain):0.0}s", HorizontalAlignment.Left, -1, 13, Colors.White);
        }
        DrawString(ThemeDB.FallbackFont, new Vector2(30, 472), $"Expired / Discarded: {_expired}", HorizontalAlignment.Left, -1, 14, new Color("ff7f7f"));
    }

    private void DrawAirportBlock(Vector2 center, string title, Color color)
    {
        var rect = new Rect2(center.X - 85, center.Y - 58, 170, 116);
        DrawRect(rect, color, true);
        DrawRect(rect, Colors.LightSkyBlue, false, 2.0f);
        DrawCircle(center + new Vector2(58, -52), 16, new Color("6f8ba4"));
        DrawString(ThemeDB.FallbackFont, center + new Vector2(-72, 8), title, HorizontalAlignment.Left, 144, 14, Colors.White);
    }

    private void DrawAircraft()
    {
        foreach (var craft in _aircraft)
        {
            var color = craft.State switch
            {
                AircraftState.InFlight => new Color("96f7b3"),
                AircraftState.Returning => new Color("9db8ff"),
                AircraftState.Unloading => new Color("f7e39e"),
                AircraftState.Maintenance => new Color("d7a3ff"),
                _ => new Color("d4e6f8")
            };

            var p = craft.Position;
            DrawPolygon(
                new PackedVector2Array(new[]
                {
                    p + new Vector2(-15, 0),
                    p + new Vector2(10, -8),
                    p + new Vector2(16, 0),
                    p + new Vector2(10, 8),
                }),
                new Color[] { color, color, color, color });

            var status = craft.Cargo == null ? $"{craft.Name} {craft.State}" : $"{craft.Name} {craft.State} ({craft.Cargo.Id})";
            DrawString(ThemeDB.FallbackFont, p + new Vector2(-40, -14), status, HorizontalAlignment.Left, -1, 12, Colors.White);
        }
    }

    private void DrawDeliveredPanel()
    {
        DrawRect(new Rect2(885, 95, 380, 390), new Color("0b1a2a"), true);
        DrawString(ThemeDB.FallbackFont, new Vector2(898, 120), "Delivered Pallets", HorizontalAlignment.Left, -1, 14, Colors.LightGreen);
        for (int i = 0; i < _deliveredList.Count; i++)
        {
            var y = 146 + i * 30;
            DrawRect(new Rect2(895, y, 360, 24), new Color("1f5a41"), true);
            DrawString(ThemeDB.FallbackFont, new Vector2(904, y + 17), _deliveredList[i], HorizontalAlignment.Left, -1, 13, Colors.White);
        }
    }

    private void DrawDashedRoute(Vector2 from, Vector2 to, int dashCount, Color color)
    {
        for (int i = 0; i < dashCount; i++)
        {
            float t0 = i / (float)dashCount;
            float t1 = (i + 0.5f) / dashCount;
            var a = from.Lerp(to, t0);
            var b = from.Lerp(to, t1);
            DrawLine(a, b, color, 2.0f);
        }
    }

    private void DrawArrow(Vector2 from, Vector2 to, Color color)
    {
        DrawLine(from, to, color, 2.0f);
        var dir = (to - from).Normalized();
        var left = to - dir * 14 + new Vector2(-dir.Y, dir.X) * 6;
        var right = to - dir * 14 + new Vector2(dir.Y, -dir.X) * 6;
        DrawLine(to, left, color, 2.0f);
        DrawLine(to, right, color, 2.0f);
    }

    private void AppendEvent(string evt)
    {
        var line = $"{_clock.SimTimeSec,6:0.0}s | {evt}";
        _events.Add(line);
        if (_events.Count > 30)
        {
            _events.RemoveAt(0);
        }
    }
}
