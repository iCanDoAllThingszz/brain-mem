import { useRef, useEffect, useState, useCallback } from 'react';
import * as d3 from 'd3';

interface GraphNode {
  id: string;
  name: string;
  zone: string;
  importance: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  rel_type: string;
}

const ZONE_COLORS: Record<string, string> = {
  episodic: '#10b981',
  semantic: '#3b82f6',
  procedural: '#f59e0b',
  concept: '#ec4899',
};

function getColor(zone: string) {
  return ZONE_COLORS[zone] || '#94a3b8';
}

export default function GraphVisualizer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simRef = useRef<d3.Simulation<GraphNode, GraphLink> | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; name: string } | null>(null);
  const transformRef = useRef({ x: 0, y: 0, k: 1 });

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8100/api/graph?limit=300');
      const json = await res.json();
      if (json.code === 0 && json.data) {
        const newNodes: GraphNode[] = json.data.nodes.map((n: any) => ({
          id: n.id,
          name: n.name,
          zone: n.zone || 'episodic',
          importance: n.importance || 5,
        }));
        const newLinks: GraphLink[] = json.data.relations.map((r: any) => ({
          source: r.from_id,
          target: r.to_id,
          rel_type: r.rel_type,
        }));
        setNodes(newNodes);
        setLinks(newLinks);
      }
    } catch {
      // Backend not running - show demo nodes
      const demo: GraphNode[] = [
        { id: '1', name: 'Memory Node A', zone: 'episodic', importance: 8 },
        { id: '2', name: 'Concept B', zone: 'semantic', importance: 6 },
        { id: '3', name: 'Skill C', zone: 'procedural', importance: 7 },
        { id: '4', name: 'Event D', zone: 'episodic', importance: 5 },
        { id: '5', name: 'Idea E', zone: 'concept', importance: 9 },
      ];
      const demoLinks: GraphLink[] = [
        { source: '1', target: '2', rel_type: 'RELATES_TO' },
        { source: '2', target: '3', rel_type: 'ENABLES' },
        { source: '3', target: '4', rel_type: 'FOLLOWS' },
        { source: '4', target: '5', rel_type: 'INSPIRED_BY' },
        { source: '5', target: '1', rel_type: 'RECALLS' },
      ];
      setNodes(demo);
      setLinks(demoLinks);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    // Stop previous simulation
    simRef.current?.stop();

    const nodesCopy = nodes.map(n => ({ ...n }));
    const linksCopy = links.map(l => ({ ...l }));

    const sim = d3.forceSimulation<GraphNode>(nodesCopy)
      .force('link', d3.forceLink<GraphNode, GraphLink>(linksCopy).id(d => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius((d: any) => d.importance * 3 + 10));

    simRef.current = sim;

    let animFrame: number;

    function draw() {
      if (!ctx) return;
      const t = transformRef.current;
      ctx.clearRect(0, 0, width, height);

      ctx.save();
      ctx.translate(t.x, t.y);
      ctx.scale(t.k, t.k);

      // Draw links
      linksCopy.forEach((link: any) => {
        const s = link.source;
        const tg = link.target;
        if (!s.x || !tg.x) return;

        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(tg.x, tg.y);
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 1.5 / t.k;
        ctx.stroke();

        // Arrow
        const angle = Math.atan2(tg.y - s.y, tg.x - s.x);
        const r = (tg.importance || 5) * 2 + 8;
        const ax = tg.x - r * Math.cos(angle);
        const ay = tg.y - r * Math.sin(angle);
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(ax - 8 / t.k * Math.cos(angle - 0.4), ay - 8 / t.k * Math.sin(angle - 0.4));
        ctx.lineTo(ax - 8 / t.k * Math.cos(angle + 0.4), ay - 8 / t.k * Math.sin(angle + 0.4));
        ctx.closePath();
        ctx.fillStyle = 'rgba(255,255,255,0.2)';
        ctx.fill();
      });

      // Draw nodes
      nodesCopy.forEach((node: any) => {
        if (!node.x) return;
        const r = (node.importance || 5) * 2 + 6;
        const color = getColor(node.zone);

        // Glow
        ctx.shadowColor = color;
        ctx.shadowBlur = 15;

        ctx.beginPath();
        ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();

        ctx.shadowBlur = 0;

        // Label
        if (t.k > 0.8) {
          const fontSize = Math.max(11, 13 / t.k);
          ctx.font = `${fontSize}px Inter, sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillStyle = 'rgba(255,255,255,0.9)';
          ctx.fillText(node.name.length > 18 ? node.name.slice(0, 18) + '…' : node.name, node.x, node.y + r + 4 / t.k);
        }
      });

      ctx.restore();
    }

    sim.on('tick', () => {
      cancelAnimationFrame(animFrame);
      animFrame = requestAnimationFrame(draw);
    });

    // Zoom & pan
    const zoom = d3.zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.1, 8])
      .on('zoom', (event) => {
        transformRef.current = { x: event.transform.x, y: event.transform.y, k: event.transform.k };
        draw();
      });
    d3.select(canvas).call(zoom);

    // Drag
    d3.select(canvas).on('mousedown', (event: any) => {
      const t = transformRef.current;
      const mx = (event.offsetX - t.x) / t.k;
      const my = (event.offsetY - t.y) / t.k;
      const node = nodesCopy.find((n: any) => {
        const r = (n.importance || 5) * 2 + 6;
        return n.x && Math.hypot(mx - n.x, my - n.y) <= r;
      }) as any;
      if (!node) return;

      node.fx = node.x;
      node.fy = node.y;
      sim.alphaTarget(0.3).restart();

      const onMove = (e: MouseEvent) => {
        const t2 = transformRef.current;
        node.fx = (e.offsetX - t2.x) / t2.k;
        node.fy = (e.offsetY - t2.y) / t2.k;
      };
      const onUp = () => {
        node.fx = null;
        node.fy = null;
        sim.alphaTarget(0);
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });

    // Tooltip on hover
    d3.select(canvas).on('mousemove', (event: any) => {
      const t = transformRef.current;
      const mx = (event.offsetX - t.x) / t.k;
      const my = (event.offsetY - t.y) / t.k;
      const node = nodesCopy.find((n: any) => {
        const r = (n.importance || 5) * 2 + 6;
        return n.x && Math.hypot(mx - n.x, my - n.y) <= r;
      });
      if (node) {
        setTooltip({ x: event.offsetX, y: event.offsetY, name: node.name });
        canvas.style.cursor = 'grab';
      } else {
        setTooltip(null);
        canvas.style.cursor = 'default';
      }
    });

    return () => {
      sim.stop();
      cancelAnimationFrame(animFrame);
      d3.select(canvas).on('mousedown', null).on('mousemove', null);
    };
  }, [nodes, links]);

  // Resize canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <canvas ref={canvasRef} style={{ display: 'block' }} />
      {tooltip && (
        <div style={{
          position: 'absolute',
          left: tooltip.x + 12,
          top: tooltip.y - 12,
          background: 'rgba(15,15,25,0.9)',
          border: '1px solid rgba(255,255,255,0.15)',
          borderRadius: 6,
          padding: '4px 10px',
          fontSize: 13,
          color: '#f8fafc',
          pointerEvents: 'none',
          backdropFilter: 'blur(8px)',
        }}>
          {tooltip.name}
        </div>
      )}

      {/* Legend */}
      <div style={{
        position: 'absolute',
        top: 100,
        left: 24,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        background: 'rgba(15,15,25,0.7)',
        backdropFilter: 'blur(8px)',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 10,
        padding: '8px 12px',
      }}>
        {Object.entries(ZONE_COLORS).map(([zone, color]) => (
          <div key={zone} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}` }} />
            <span style={{ color: '#94a3b8', textTransform: 'capitalize' }}>{zone}</span>
          </div>
        ))}
      </div>

      {nodes.length === 0 && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%,-50%)',
          textAlign: 'center',
          color: 'rgba(148,163,184,0.4)',
          pointerEvents: 'none',
        }}>
          <div style={{ fontSize: 48 }}>🧠</div>
          <p style={{ marginTop: 8, fontSize: 14 }}>Connecting to neural graph...</p>
        </div>
      )}
    </div>
  );
}
