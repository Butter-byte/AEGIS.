type EventLogProps = {
  events: string[];
};

function EventLog({ events }: EventLogProps) {
  return (
    <div className="event-log">
      <div className="event-log-header">
        <span>SYSTEM EVENTS</span>
        <span className="event-count">{events.length}</span>
      </div>

      <div className="event-list">
        {events.map((event, index) => (
          <div className="event-item" key={`${event}-${index}`}>
            <span className="event-dot" />
            <span>{event}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default EventLog;