// Operational timeline. Every entry is a real backend WS event or a real
// frontend action (fault injection / reset) — nothing is fabricated.

export type LogEntry = {
  text: string;
  kind: "info" | "fault" | "ok" | "bad" | "boundary";
};

type EventLogProps = {
  events: LogEntry[];
};

function EventLog({ events }: EventLogProps) {
  return (
    <div className="event-log">
      <div className="event-log-header">
        <span>SYSTEM EVENTS</span>
        <span className="event-count">{events.length}</span>
      </div>

      <div className="event-list">
        {events.map((entry, index) =>
          entry.kind === "boundary" ? (
            <div className="event-boundary" key={index}>
              <span>{entry.text}</span>
            </div>
          ) : (
            <div className={`event-item event-${entry.kind}`} key={index}>
              <span className="event-dot" />
              <span>{entry.text}</span>
            </div>
          ),
        )}
      </div>
    </div>
  );
}

export default EventLog;
