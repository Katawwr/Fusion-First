import React from "react";

// The FF ("friendly fire") pixel monogram: white on brand purple. One pixel is knocked out of the second F's
// stem below the junction so both letters still read. Same grid as public/ff.svg.
const FF_GRID = [
  "##########",
  "##########",
  "##...##...",
  "##...##...",
  "#########.",
  "#########.",
  "##........",
  "##...##...",
  "##...##...",
  "##...##...",
];

const AREA = 36;
const CELL = AREA / FF_GRID.length;
const OFF = (64 - AREA) / 2;

export default function BrandMark({ size = 28 }) {
  return (
    <svg aria-hidden viewBox="0 0 64 64" width={size} height={size} className="brand-mark" shapeRendering="crispEdges">
      <rect width="64" height="64" rx="14" fill="#504d9a" shapeRendering="geometricPrecision" />
      <g fill="#ffffff">
        {FF_GRID.flatMap((row, r) =>
          [...row].map((ch, c) =>
            ch === "#" ? <rect key={`${r}-${c}`} x={OFF + c * CELL} y={OFF + r * CELL} width={CELL} height={CELL} /> : null,
          ),
        )}
      </g>
    </svg>
  );
}
