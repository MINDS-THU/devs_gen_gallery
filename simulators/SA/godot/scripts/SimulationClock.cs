public sealed class SimulationClock
{
    public double SimTimeSec { get; private set; }
    public double TimeScale { get; set; } = 1.0;

    public void Advance(double realDeltaSec)
    {
        SimTimeSec += realDeltaSec * TimeScale;
    }
}
