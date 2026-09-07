export function Sparkline({
    data,
    color,
    gradientId,
}: {
    data: number[];
    color: string;
    gradientId: string;
}) {
    const max = Math.max(...data, 1);
    const min = 0;

    const width = 100;
    const height = 40;
    const padding = 4;
    const usableHeight = height - padding * 2;

    const points = data.map((val, i) => {
        const x = (i / (data.length - 1)) * width;
        const y = padding + usableHeight - ((val - min) / (max - min)) * usableHeight;
        return `${x},${y}`;
    });

    const polylinePoints = points.join(" ");
    const fillPath = `M0,${height} L${points[0]} ${points.slice(1).map(p => `L${p}`).join(" ")} L${width},${height} Z`;

    return (
        <svg
            width="100%"
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="none"
            style={{ display: 'block', overflow: 'visible' }}
        >
            <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity="0.5" />
                    <stop offset="100%" stopColor={color} stopOpacity="0.0" />
                </linearGradient>
            </defs>
            <path d={fillPath} fill={`url(#${gradientId})`} />
            <polyline
                points={polylinePoints}
                fill="none"
                stroke={color}
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
                strokeLinejoin="round"
            />
        </svg>
    );
}
