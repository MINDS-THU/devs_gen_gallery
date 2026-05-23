using Godot;
using System;

public sealed class AircraftAgent
{
    private readonly double _flightSec;
    private readonly double _unloadSec;
    private readonly double _returnSec;
    private readonly double _maintenanceSec;
    private double _stateUntilSec;
    private double _phaseStartSec;
    private Vector2 _originPos;
    private Vector2 _destinationPos;

    public string Name { get; }
    public AircraftState State { get; private set; } = AircraftState.Idle;
    public Pallet? Cargo { get; private set; }
    public Vector2 Position { get; private set; }

    public AircraftAgent(string name, SimulationConfig config, Vector2 originPos)
    {
        Name = name;
        _flightSec = config.FlightSec;
        _unloadSec = config.UnloadSec;
        _returnSec = config.ReturnSec;
        _maintenanceSec = config.MaintenanceSec;
        _originPos = originPos;
        _destinationPos = originPos;
        Position = originPos;
    }

    public bool IsIdle => State == AircraftState.Idle && Cargo == null;

    public bool TryAssign(Pallet pallet, double nowSec, Vector2 originPos, Vector2 destinationPos, Action<string> onEvent)
    {
        if (!IsIdle)
        {
            return false;
        }

        Cargo = pallet;
        _originPos = originPos;
        _destinationPos = destinationPos;
        Position = _originPos;

        State = AircraftState.InFlight;
        _phaseStartSec = nowSec;
        _stateUntilSec = nowSec + _flightSec;
        onEvent($"{Name} assigned {pallet.Id}, departing.");
        return true;
    }

    public void Update(double nowSec, Action<Pallet, double> onDelivered, Action<string> onEvent)
    {
        switch (State)
        {
            case AircraftState.Idle:
                Position = _originPos;
                break;
            case AircraftState.InFlight:
            {
                var t = Mathf.Clamp((float)((nowSec - _phaseStartSec) / _flightSec), 0f, 1f);
                Position = _originPos.Lerp(_destinationPos, t);
                if (nowSec >= _stateUntilSec)
                {
                    State = AircraftState.Unloading;
                    _phaseStartSec = nowSec;
                    _stateUntilSec = nowSec + _unloadSec;
                    onEvent($"{Name} arrived destination, unloading {Cargo?.Id}.");
                }
                break;
            }
            case AircraftState.Unloading:
                Position = _destinationPos;
                if (nowSec >= _stateUntilSec)
                {
                    if (Cargo != null)
                    {
                        onDelivered(Cargo, nowSec);
                    }
                    State = AircraftState.Returning;
                    _phaseStartSec = nowSec;
                    _stateUntilSec = nowSec + _returnSec;
                    onEvent($"{Name} unload complete, returning.");
                }
                break;
            case AircraftState.Returning:
            {
                var t = Mathf.Clamp((float)((nowSec - _phaseStartSec) / _returnSec), 0f, 1f);
                Position = _destinationPos.Lerp(_originPos, t);
                if (nowSec >= _stateUntilSec)
                {
                    Cargo = null;
                    State = AircraftState.Maintenance;
                    _phaseStartSec = nowSec;
                    _stateUntilSec = nowSec + _maintenanceSec;
                    onEvent($"{Name} at origin, maintenance.");
                }
                break;
            }
            case AircraftState.Maintenance:
                Position = _originPos;
                if (nowSec >= _stateUntilSec)
                {
                    State = AircraftState.Idle;
                    onEvent($"{Name} maintenance complete, idle.");
                }
                break;
            default:
                throw new ArgumentOutOfRangeException();
        }
    }
}
