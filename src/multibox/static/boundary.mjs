// Cached geometry from the approved repo mockup, Library version 3.
// The separate 1248×768 frame surrounds an unchanged 1200×720 playable canvas.
// Players are clipped by that inner canvas and can never cover the decoration.
export function createBoundary() {
  const boundaryCanvas = document.createElement("canvas");
  boundaryCanvas.width = 1248;
  boundaryCanvas.height = 768;
  const boundaryCtx = boundaryCanvas.getContext("2d");
  const boundaryWidth = 24;
  const weaveGround = "#c5c8bd";
  function band(points, color, width = 6) {
    boundaryCtx.beginPath();
    boundaryCtx.moveTo(...points[0]);
    for (const point of points.slice(1)) boundaryCtx.lineTo(...point);
    boundaryCtx.strokeStyle = color;
    boundaryCtx.lineWidth = width;
    boundaryCtx.lineCap = "butt";
    boundaryCtx.lineJoin = "miter";
    boundaryCtx.stroke();
  }
  for (const [x, y, angle, length] of [
    [0, 0, 0, 1248],
    [1248, 0, Math.PI / 2, 768],
    [1248, 768, Math.PI, 1248],
    [0, 768, -Math.PI / 2, 768],
  ]) {
    boundaryCtx.save();
    boundaryCtx.translate(x, y);
    boundaryCtx.rotate(angle);
    boundaryCtx.fillStyle = weaveGround;
    boundaryCtx.fillRect(0, 0, length, boundaryWidth);
    // An even number of lane exchanges meets the same square elbow at both ends.
    const units = Math.floor((length - 48) / 96) * 2;
    const step = (length - 48) / units;
    for (let unit = 0; unit < units; unit++) {
      const u = (position) => 24 + unit * step + (position * step) / 48;
      const top = unit % 2 === 0 ? 6 : 18;
      const bottom = 24 - top;
      // Black takes a direct right-angle turn between lanes.
      band(
        [
          [u(0), top],
          [u(16), top],
          [u(16), bottom],
          [u(48), bottom],
        ],
        "#20231f",
      );
      // White takes the middle lane briefly, crossing the black vertical.
      band(
        [
          [u(0), bottom],
          [u(8), bottom],
          [u(8), 12],
          [u(24), 12],
          [u(24), top],
          [u(48), top],
        ],
        "#fafaf5",
      );
      const over =
        unit % 2 === 0
          ? [
              [u(16), 6],
              [u(16), 18],
            ]
          : [
              [u(10), 12],
              [u(22), 12],
            ];
      // Clearance removes the underpass at the crossing; the overpass is continuous.
      band(over, weaveGround, 10);
      band(over, unit % 2 === 0 ? "#20231f" : "#fafaf5");
    }
    boundaryCtx.restore();
  }
  // Four nested square elbows continue both bands around the corners.
  for (const [x, y, angle] of [
    [1248, 0, 0],
    [1248, 768, Math.PI / 2],
    [0, 768, Math.PI],
    [0, 0, -Math.PI / 2],
  ]) {
    boundaryCtx.save();
    boundaryCtx.translate(x, y);
    boundaryCtx.rotate(angle);
    boundaryCtx.fillStyle = weaveGround;
    boundaryCtx.fillRect(-24, 0, 24, 24);
    band(
      [
        [-24, 6],
        [-6, 6],
        [-6, 24],
      ],
      "#20231f",
    );
    band(
      [
        [-24, 18],
        [-18, 18],
        [-18, 24],
      ],
      "#fafaf5",
    );
    boundaryCtx.restore();
  }

  return boundaryCanvas;
}
