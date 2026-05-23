public sealed class Pallet
{
    public string Id { get; init; } = "";
    public double GenerationTime { get; init; }
    public double DeadlineTime { get; init; }
}

public enum AircraftState
{
    Idle,
    InFlight,
    Unloading,
    Returning,
    Maintenance
}
