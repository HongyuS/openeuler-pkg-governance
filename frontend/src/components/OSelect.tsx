import { useEffect, useRef, useState } from "react";

export interface OOption {
  id: string;
  label: string;
}

/** openEuler 风格下拉选择器（替代原生 select）：点击展开、上下键导航、回车选中、ESC/点外部关闭 */
export function OSelect(props: {
  value: string;
  options: OOption[];
  onChange: (v: string) => void;
  label?: string;
  placeholder?: string;
  minWidth?: number;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [up, setUp] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (open && active >= 0) {
      listRef.current?.children[active]?.scrollIntoView({ block: "nearest" });
    }
  }, [active, open]);

  const cur = props.options.find((o) => o.id === props.value);
  const pick = (id: string) => {
    props.onChange(id);
    setOpen(false);
  };
  const toggle = () => {
    if (!open && rootRef.current) {
      const r = rootRef.current.getBoundingClientRect();
      setUp(window.innerHeight - r.bottom < 240 && r.top > 240);
    }
    setOpen((o) => !o);
    setActive(Math.max(0, props.options.findIndex((o) => o.id === props.value)));
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      toggle();
      return;
    }
    if (!open) return;
    if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(props.options.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(props.options[active].id); }
    else if (e.key === "Tab") setOpen(false);
  };

  return (
    <div className={`oselect${props.label ? " stream-select" : ""}`} ref={rootRef} onKeyDown={onKey}>
      {props.label ? <label>{props.label}</label> : null}
      <button
        type="button"
        className={`oselect-btn${open ? " open" : ""}`}
        style={props.minWidth ? { minWidth: props.minWidth } : undefined}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={toggle}
      >
        <span className="oselect-value">{cur ? cur.label : (props.placeholder ?? "选择…")}</span>
        <span className="oselect-arrow">▾</span>
      </button>
      {open ? (
        <ul className={`oselect-list${up ? " up" : ""}`} role="listbox" ref={listRef}>
          {props.options.map((o, i) => (
            <li
              key={o.id || "_"}
              role="option"
              aria-selected={o.id === props.value}
              className={`oselect-item${o.id === props.value ? " sel" : ""}${i === active ? " act" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(o.id)}
            >
              <span className="oselect-value">{o.label}</span>
              {o.id === props.value ? <span className="oselect-check">✓</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
