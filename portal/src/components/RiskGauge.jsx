/**
 * Animated SVG Risk Gauge Ring
 * Props: score (0-100), size (default 180)
 */
export default function RiskGauge({ score = 0, size = 180 }) {
  const r = size * 0.4;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;
  const ratio = Math.min(score / 100, 1);
  const dashOffset = circumference * (1 - ratio);

  const color =
    score >= 85 ? '#ef4444' :
    score >= 60 ? '#f97316' :
    score >= 30 ? '#f59e0b' :
    '#10b981';

  const glow = score >= 60
    ? `0 0 20px ${color}44`
    : 'none';

  return (
    <div className="risk-gauge-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background track */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={size * 0.09}
        />
        {/* Animated progress arc */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke={color}
          strokeWidth={size * 0.09}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{
            transition: 'stroke-dashoffset 0.8s cubic-bezier(0.4,0,0.2,1), stroke 0.5s ease',
            filter: glow !== 'none' ? `drop-shadow(0 0 8px ${color}88)` : 'none',
          }}
        />
      </svg>
      <div className="risk-gauge-center">
        <div className="risk-gauge-score" style={{ color, fontSize: size * 0.16 }}>
          {Math.round(score)}
        </div>
        <div className="risk-gauge-label" style={{ fontSize: size * 0.07 }}>RISK</div>
      </div>
    </div>
  );
}
