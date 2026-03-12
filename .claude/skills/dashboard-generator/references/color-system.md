# Color System Reference

This file defines the complete Tailwind CSS color palette and Chart.js color configuration for Mode C dashboard generation.

---

## Tailwind CSS Classes

### Base Layout
```
Background: bg-gray-950 (page), bg-gray-900 (cards), bg-gray-800 (table rows)
Text primary: text-white
Text secondary: text-gray-300
Text muted: text-gray-500
Borders: border-gray-700
```

### Positive / Bullish
```
Color: emerald
- Text: text-emerald-400
- Background: bg-emerald-900/30 (translucent for cards)
- Border: border-emerald-600
- Badge: bg-emerald-600 text-white
- Number display: text-emerald-400
```

### Negative / Bearish
```
Color: red
- Text: text-red-400
- Background: bg-red-900/30
- Border: border-red-600
- Badge: bg-red-600 text-white
- Number display: text-red-400
```

### Warning / Neutral / Caution
```
Color: amber
- Text: text-amber-400
- Background: bg-amber-900/30
- Border: border-amber-600
- Badge: bg-amber-600 text-white
```

### Information / Blue
```
Color: blue
- Text: text-blue-400
- Background: bg-blue-900/30
- Border: border-blue-600
```

---

## Data Mode Badges

```html
<!-- Enhanced Mode -->
<span class="bg-emerald-600 text-white text-xs font-semibold px-2.5 py-1 rounded-full">
  ✅ Enhanced Mode
</span>

<!-- Standard Mode (US) -->
<span class="bg-amber-600 text-white text-xs font-semibold px-2.5 py-1 rounded-full">
  ⚠ Standard Mode
</span>

<!-- Korean Stock -->
<span class="bg-blue-600 text-white text-xs font-semibold px-2.5 py-1 rounded-full">
  🇰🇷 KR Standard Mode
</span>
```

---

## R/R Score Badge

```html
<!-- R/R Score > 3 (Attractive) — Emerald -->
<div class="bg-emerald-600 text-white text-2xl font-bold px-6 py-3 rounded-xl inline-block">
  R/R Score: {value}
  <div class="text-sm font-normal">Attractive</div>
</div>

<!-- R/R Score 1–3 (Neutral) — Amber -->
<div class="bg-amber-600 text-white text-2xl font-bold px-6 py-3 rounded-xl inline-block">
  R/R Score: {value}
  <div class="text-sm font-normal">Neutral</div>
</div>

<!-- R/R Score < 1 (Unfavorable) — Red -->
<div class="bg-red-600 text-white text-2xl font-bold px-6 py-3 rounded-xl inline-block">
  R/R Score: {value}
  <div class="text-sm font-normal">Unfavorable</div>
</div>
```

---

## Scenario Cards

```html
<!-- Bull scenario card -->
<div class="bg-emerald-900/30 border border-emerald-600 rounded-xl p-5">
  <div class="text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-1">Bull Case</div>
  <div class="text-emerald-400 text-3xl font-bold">${target}</div>
  <div class="text-emerald-300 text-lg">{return_pct}</div>
  <div class="text-gray-400 text-xs mt-2">{probability}% probability</div>
  <div class="text-gray-300 text-sm mt-2 border-t border-emerald-800 pt-2">{key_assumption}</div>
</div>

<!-- Base scenario card -->
<div class="bg-blue-900/30 border border-blue-600 rounded-xl p-5">
  <div class="text-blue-400 text-xs font-semibold uppercase tracking-wider mb-1">Base Case</div>
  <!-- same pattern with blue colors -->
</div>

<!-- Bear scenario card -->
<div class="bg-red-900/30 border border-red-600 rounded-xl p-5">
  <div class="text-red-400 text-xs font-semibold uppercase tracking-wider mb-1">Bear Case</div>
  <!-- same pattern with red colors -->
</div>
```

---

## Verdict Badge

```html
<!-- Overweight / 비중확대 -->
<span class="bg-emerald-600 text-white font-bold px-4 py-1.5 rounded-lg">Overweight</span>

<!-- Neutral / 중립 -->
<span class="bg-amber-600 text-white font-bold px-4 py-1.5 rounded-lg">Neutral</span>

<!-- Underweight / 비중축소 -->
<span class="bg-red-600 text-white font-bold px-4 py-1.5 rounded-lg">Underweight</span>
```

---

## Source Tag Styles (inline in text)

```html
<code class="bg-gray-700 text-blue-300 text-xs px-1.5 py-0.5 rounded">[API]</code>
<code class="bg-gray-700 text-emerald-300 text-xs px-1.5 py-0.5 rounded">[Calculated]</code>
<code class="bg-gray-700 text-amber-300 text-xs px-1.5 py-0.5 rounded">[Web]</code>
<code class="bg-gray-700 text-amber-300 text-xs px-1.5 py-0.5 rounded">[1S]</code>
<code class="bg-red-900 text-red-300 text-xs px-1.5 py-0.5 rounded">[Unverified]</code>
<code class="bg-gray-700 text-purple-300 text-xs px-1.5 py-0.5 rounded">[DART]</code>
```

---

## Chart.js Color Configuration

### Price Chart (Line)
```javascript
priceChart: {
  borderColor: '#3b82f6',          // blue-500
  backgroundColor: 'rgba(59,130,246,0.08)',
  borderWidth: 2,
  pointRadius: 0,
  tension: 0.3
}
```

### Revenue Bar Chart
```javascript
revenueBar: {
  backgroundColor: 'rgba(59,130,246,0.7)',  // blue-500
  borderColor: '#3b82f6',
  borderWidth: 1
}
operatingIncomeBar: {
  backgroundColor: 'rgba(16,185,129,0.7)',  // emerald-500
  borderColor: '#10b981',
  borderWidth: 1
}
```

### Margin Trend Chart (Multi-line)
```javascript
grossMarginLine: {
  borderColor: '#10b981',   // emerald-500
  backgroundColor: 'transparent',
  borderWidth: 2,
  pointRadius: 3
}
operatingMarginLine: {
  borderColor: '#3b82f6',   // blue-500
  backgroundColor: 'transparent',
  borderWidth: 2,
  pointRadius: 3
}
netMarginLine: {
  borderColor: '#f59e0b',   // amber-500
  backgroundColor: 'transparent',
  borderWidth: 2,
  pointRadius: 3
}
```

### Peer Comparison Bar
```javascript
peerBar: {
  backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'],
  borderWidth: 0,
  borderRadius: 4
}
```

---

## Global Chart.js Options

```javascript
const globalChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: { color: '#d1d5db', font: { size: 12 } }
    },
    tooltip: {
      backgroundColor: '#1f2937',
      titleColor: '#f9fafb',
      bodyColor: '#d1d5db',
      borderColor: '#374151',
      borderWidth: 1
    }
  },
  scales: {
    x: {
      grid: { color: '#374151' },
      ticks: { color: '#9ca3af' }
    },
    y: {
      grid: { color: '#374151' },
      ticks: { color: '#9ca3af' }
    }
  }
};
```

---

## Korean Language Font

For Korean output, add this to `<head>`:
```html
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
```

And apply:
```html
<body class="font-['Noto_Sans_KR',_sans-serif]">
```

For English output, use:
```html
<body class="font-sans">
```
