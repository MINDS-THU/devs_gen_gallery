public sealed class SimulationConfig
{
    public double PalletIntervalSec { get; set; } = 10.0;
    public double PalletExpirationSec { get; set; } = 20.0;
    public double FlightSec { get; set; } = 30.0;
    public double UnloadSec { get; set; } = 2.0;
    public double ReturnSec { get; set; } = 30.0;
    public double MaintenanceSec { get; set; } = 10.0;
    public double TotalDurationSec { get; set; } = 120.0;
    public int AircraftCount { get; set; } = 2;
    public double TimeScale { get; set; } = 5.0;
}
