using System;
using System.Collections.Generic;

public sealed class LoadingQueue
{
    private readonly Queue<Pallet> _queue = new();

    public int Count => _queue.Count;
    public IEnumerable<Pallet> Items => _queue;

    public void Enqueue(Pallet pallet)
    {
        _queue.Enqueue(pallet);
    }

    public Pallet? DequeueNext()
    {
        if (_queue.Count == 0)
        {
            return null;
        }
        return _queue.Dequeue();
    }

    public void ExpireDue(double nowSec, Action<Pallet> onExpired)
    {
        while (_queue.Count > 0)
        {
            var head = _queue.Peek();
            if (nowSec < head.DeadlineTime)
            {
                break;
            }
            var expired = _queue.Dequeue();
            onExpired(expired);
        }
    }
}
