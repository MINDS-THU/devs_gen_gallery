using System.Collections.Generic;

public sealed class FleetCoordinator
{
    public void AssignAvailable(LoadingQueue queue, List<AircraftAgent> aircraft, double nowSec, Godot.Vector2 originPos, Godot.Vector2 destinationPos, System.Action<string> onEvent)
    {
        foreach (var craft in aircraft)
        {
            if (!craft.IsIdle || queue.Count == 0)
            {
                continue;
            }

            var pallet = queue.DequeueNext();
            if (pallet == null)
            {
                return;
            }

            craft.TryAssign(pallet, nowSec, originPos, destinationPos, onEvent);
        }
    }
}
