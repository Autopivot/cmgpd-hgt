// Hexagon glyph geometry. Pointy-top hex.
// side points ordered: 0=top, 1=top-right, 2=bottom-right, 3=bottom, 4=bottom-left, 5=top-left

export function hexCorners(cx, cy, r) {
  const pts = []
  for (let i = 0; i < 6; i++) {
    const ang = (Math.PI / 3) * i - Math.PI / 2
    pts.push([cx + r * Math.cos(ang), cy + r * Math.sin(ang)])
  }
  return pts
}

export function hexPath(cx, cy, r) {
  return hexCorners(cx, cy, r)
    .map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(2) + ',' + p[1].toFixed(2))
    .join('') + 'Z'
}

// Return six edge segments as [ [x1,y1,x2,y2], ... ].
export function hexEdges(cx, cy, r) {
  const c = hexCorners(cx, cy, r)
  return c.map((p, i) => {
    const q = c[(i + 1) % 6]
    return [p[0], p[1], q[0], q[1]]
  })
}
