using System;

public sealed class PalletSource
{
    private readonly double _intervalSec;
    private double _nextGenerationSec;
    private int _counter = 11;

    public PalletSource(double intervalSec)
    {
        _intervalSec = intervalSec;
        _nextGenerationSec = 0.0;
    }

    public void Update(double nowSec, double expirationSec, Action<Pallet> onGenerate)
    {
        while (nowSec >= _nextGenerationSec)
        {
            var pallet = new Pallet
            {
                Id = $"P-{_counter:000}",
                GenerationTime = _nextGenerationSec,
                DeadlineTime = _nextGenerationSec + expirationSec
            };
            _counter++;
            onGenerate(pallet);
            _nextGenerationSec += _intervalSec;
        }
    }
}
