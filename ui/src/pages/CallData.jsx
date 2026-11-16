import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Database as DbIcon,
  Eye,
  Refresh,
  Search,
  Trash,
  X,
} from "../components/Icons";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";

const PAGE = 25;

function bytes(n) {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const WIDE = { text: 320, error: 280, recording_url: 220, message: 320 };

function Cell({ column, value }) {
  if (value === null || value === undefined || value === "")
    return <span className="faint">-</span>;
  if (typeof value === "boolean") return <span className="pill">{String(value)}</span>;
  if (column.endsWith("_at")) {
    return (
      <span className="nowrap" title={value}>
        {relativeTime(value)}
      </span>
    );
  }
  if (typeof value === "object") {
    return <span className="mono tiny faint">{JSON.stringify(value).slice(0, 48)}…</span>;
  }
  const text = String(value);
  return (
    <span className="ellipsis" style={{ display: "block", maxWidth: WIDE[column] || 170 }} title={text}>
      {text}
    </span>
  );
}

export default function CallData() {
  const { user, can } = useAuth();
  const toast = useToast();
  const isAdmin = can("data.delete");

  const [tables, setTables] = useState(null);
  const [notice, setNotice] = useState("");
  const [database, setDatabase] = useState("");
  const [table, setTable] = useState("call_sessions");
  const [page, setPage] = useState(null);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [term, setTerm] = useState("");
  const [everyColumn, setEveryColumn] = useState(false);
  const [detail, setDetail] = useState(null);
  const [days, setDays] = useState("");
  const [confirming, setConfirming] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadTables = useCallback(async () => {
    try {
      const payload = await api.dataTables();
      setTables(payload.tables || []);
      setDatabase(payload.database || "");
      setNotice(payload.error || "");
    } catch (e) {
      setTables([]);
      setNotice(e.message);
    }
  }, []);

  const loadRows = useCallback(async () => {
    try {
      setPage(await api.dataRows(table, { limit: PAGE, offset, q: term }));
      setError("");
    } catch (e) {
      setPage(null);
      setError(e.message);
    }
  }, [table, offset, term]);

  useEffect(() => {
    loadTables();
  }, [loadTables]);

  useEffect(() => {
    loadRows();
  }, [loadRows]);

  useEffect(() => {
    const id = setTimeout(() => {
      setTerm(query.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(id);
  }, [query]);

  const meta = useMemo(
    () => (tables || []).find((t) => t.table === table) || null,
    [tables, table]
  );

  const total = page?.total || 0;
  const rows = page?.rows || [];
  const columns = everyColumn ? page?.columns || [] : page?.primary || page?.columns || [];
  const hidden = (page?.columns?.length || 0) - (page?.primary?.length || 0);
  const stored = (tables || []).reduce((sum, t) => sum + t.rows, 0);

  function choose(next) {
    if (next === table) return;
    setTable(next);
    setOffset(0);
    setQuery("");
    setTerm("");
    setDetail(null);
    setConfirming("");
    setEveryColumn(false);
    setPage(null);
  }

  async function openRow(id) {
    setDetail({ id, loading: true, row: null });
    try {
      const payload = await api.dataRow(table, id);
      setDetail({ id, loading: false, row: payload.row });
    } catch (e) {
      setDetail(null);
      toast.error(e.message);
    }
  }

  async function run(action) {
    setBusy(true);
    try {
      const result = await action();
      toast.ok(result.message || "Done");
      setDetail(null);
      setConfirming("");
      await Promise.all([loadTables(), loadRows()]);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  const cutoff = days.trim() === "" ? 0 : Math.max(0, Number(days) || 0);
  const cutoffLabel = cutoff ? `older than ${cutoff} day${cutoff === 1 ? "" : "s"}` : "every row";

  return (
    <div className="page">
      <div className="page-head page-head-row">
        <div style={{ flex: 1, minWidth: 260 }}>
          <h1>Database</h1>
          <p>Every row the voice stack has stored, plus the brain's own history.</p>
          {database && <p className="mono tiny faint ellipsis">{database}</p>}
        </div>
        <div className="row">
          <button
            className="btn btn-ghost btn-icon btn-sm"
            onClick={() => {
              loadTables();
              loadRows();
            }}
            aria-label="Refresh"
          >
            <Refresh size={14} />
          </button>
          {isAdmin &&
            (confirming === "all" ? (
              <div className="row" style={{ gap: 4 }}>
                <button
                  className="btn btn-danger btn-sm"
                  disabled={busy}
                  onClick={() => run(() => api.purgeAllData(cutoff))}
                >
                  Delete {cutoffLabel}, every table
                </button>
                <button
                  className="btn btn-ghost btn-icon btn-sm"
                  onClick={() => setConfirming("")}
                  aria-label="Keep"
                >
                  <X size={14} />
                </button>
              </div>
            ) : (
              <button className="btn btn-sm" disabled={!stored} onClick={() => setConfirming("all")}>
                <Trash size={14} />
                Clear all call data
              </button>
            ))}
        </div>
      </div>

      {notice && (
        <div className="notice warn" style={{ marginBottom: 14 }}>
          <Alert size={15} />
          <span>{notice}</span>
        </div>
      )}

      {!isAdmin && (
        <div className="notice" style={{ marginBottom: 14 }}>
          <DbIcon size={15} />
          <span>You can read every row here. Deleting one needs the “Delete data” permission.</span>
        </div>
      )}

      <div className="tabgrid" style={{ marginBottom: 14 }}>
        {(tables || []).map((entry) => (
          <button
            key={entry.table}
            className={`datatab ${entry.table === table ? "on" : ""}`}
            onClick={() => choose(entry.table)}
          >
            <div className="datatab-name ellipsis">
              {entry.label}
              {entry.remote && <span className="datatab-tag">brain db</span>}
            </div>
            <div className="datatab-count">
              {entry.rows}
              <span className="datatab-unit">rows</span>
            </div>
            <div className="datatab-meta ellipsis">
              {entry.error
                ? "unreachable"
                : entry.exists
                ? `${bytes(entry.bytes)} · ${entry.newest ? relativeTime(entry.newest) : "empty"}`
                : "not created yet"}
            </div>
          </button>
        ))}
        {!tables &&
          [0, 1, 2, 3, 4, 5].map((n) => <div key={n} className="skeleton" style={{ height: 74 }} />)}
      </div>

      <section className="card">
        <div className="card-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 className="row" style={{ gap: 8 }}>
              <span className="mono">{table}</span>
              <span className="tiny faint">
                {total} row{total === 1 ? "" : "s"}
              </span>
              {meta?.remote && <span className="pill">chatbot database</span>}
            </h3>
            <p>
              {meta?.blurb} {meta?.note}
            </p>
          </div>
          <div className="searchbar" style={{ maxWidth: 260 }}>
            <Search size={15} />
            <input
              className="searchinput"
              placeholder="Find a number, ref or word said"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query && (
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setQuery("")}>
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        <div className="card-body databar">
          {hidden > 0 && (
            <button className="btn btn-sm" onClick={() => setEveryColumn((v) => !v)}>
              {everyColumn ? "Key columns" : `All ${page?.columns?.length} columns`}
            </button>
          )}
          <span className="tiny faint">
            {everyColumn
              ? "Scrolls sideways. Open a row to read the same thing stacked."
              : hidden > 0
              ? `${hidden} more column${hidden === 1 ? "" : "s"} and the full record are on each row.`
              : "The full record is on each row."}
          </span>
          <div className="grow" />
          {isAdmin && (
            <>
              <span className="tiny faint nowrap">Delete rows older than</span>
              <input
                className="input mono"
                style={{ width: 76 }}
                type="number"
                min="0"
                placeholder="all"
                value={days}
                onChange={(e) => setDays(e.target.value)}
              />
              <span className="tiny faint">days</span>
              {confirming === "table" ? (
                <div className="row" style={{ gap: 4 }}>
                  <button
                    className="btn btn-danger btn-sm"
                    disabled={busy}
                    onClick={() => run(() => api.purgeDataTable(table, cutoff))}
                  >
                    Delete {cutoffLabel}
                  </button>
                  <button
                    className="btn btn-ghost btn-icon btn-sm"
                    onClick={() => setConfirming("")}
                    aria-label="Keep"
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : (
                <button
                  className="btn btn-sm nowrap"
                  disabled={!meta?.rows}
                  onClick={() => setConfirming("table")}
                >
                  <Trash size={14} />
                  Purge table
                </button>
              )}
            </>
          )}
        </div>

        {detail && (
          <div className="card-body">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
              <div className="eyebrow">
                {table} · row {detail.id}
              </div>
              <button
                className="btn btn-ghost btn-icon btn-sm"
                onClick={() => setDetail(null)}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>
            {detail.loading ? (
              <div className="skeleton" style={{ height: 120 }} />
            ) : (
              <RowDetail row={detail.row} />
            )}
          </div>
        )}

        {error && (
          <div className="card-body">
            <div className="notice warn">
              <Alert size={15} />
              <span>{error}</span>
            </div>
          </div>
        )}

        {!page ? (
          <div className="card-body stack">
            <div className="skeleton" style={{ height: 22 }} />
            <div className="skeleton" style={{ height: 22 }} />
            <div className="skeleton" style={{ height: 22 }} />
          </div>
        ) : rows.length === 0 ? (
          <div className="empty">
            <h4>{term ? "Nothing matches" : "No rows"}</h4>
            <p>
              {term
                ? "Clear the search to see everything in this table."
                : page.missing
                ? "This table has not been created yet. It appears on the first call."
                : "Nothing has been stored in this table yet."}
            </p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table datatable">
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                  <th style={{ width: 84 }} />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    className={detail?.id === row.id ? "on" : ""}
                    onClick={() => openRow(row.id)}
                  >
                    {columns.map((column) => (
                      <td key={column} className={column === "id" ? "mono small" : "small"}>
                        <Cell column={column} value={row[column]} />
                      </td>
                    ))}
                    <td onClick={(e) => e.stopPropagation()}>
                      {confirming === `row:${row.id}` ? (
                        <div className="row" style={{ gap: 4 }}>
                          <button
                            className="btn btn-danger btn-sm"
                            disabled={busy}
                            onClick={() => run(() => api.deleteDataRow(table, row.id))}
                          >
                            Delete
                          </button>
                          <button
                            className="btn btn-ghost btn-icon btn-sm"
                            onClick={() => setConfirming("")}
                            aria-label="Keep"
                          >
                            <X size={13} />
                          </button>
                        </div>
                      ) : (
                        <div className="row" style={{ gap: 4 }}>
                          <button
                            className="btn btn-ghost btn-icon btn-sm"
                            onClick={() => openRow(row.id)}
                            title="Everything stored on this row"
                            aria-label="Open row"
                          >
                            <Eye size={13} />
                          </button>
                          <button
                            className="btn btn-ghost btn-icon btn-sm"
                            disabled={!isAdmin}
                            onClick={() => setConfirming(`row:${row.id}`)}
                            title={isAdmin ? meta?.note || "Delete this row" : "Needs the Delete data permission"}
                            aria-label="Delete row"
                          >
                            <Trash size={13} />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {total > PAGE && (
          <div className="card-body row" style={{ justifyContent: "space-between" }}>
            <span className="tiny faint">
              {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
            </span>
            <div className="row" style={{ gap: 6 }}>
              <button
                className="btn btn-sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                Newer
              </button>
              <button
                className="btn btn-sm"
                disabled={offset + PAGE >= total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Older
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function spoken(message) {
  const data = message.data || {};
  const role = message.role || message.type || data.type || "-";
  return {
    role,
    human: role === "user" || role === "human",
    text: message.text || data.content || message.content || JSON.stringify(message),
  };
}

function RowDetail({ row }) {
  if (!row) return null;

  const messages = Array.isArray(row.messages) ? row.messages : null;
  const single = !messages && row.message && typeof row.message === "object" ? row.message : null;
  const chat = messages || (single ? [single] : null);

  const fields = Object.entries(row).filter(([key]) => !(chat && (key === "messages" || key === "message")));

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="rowfields">
        {fields.map(([key, value]) => (
          <div key={key} className="rowfield">
            <div className="rowfield-k mono tiny">{key}</div>
            <div className="rowfield-v small">
              {value === null || value === undefined || value === "" ? (
                <span className="faint">-</span>
              ) : typeof value === "object" ? (
                <pre className="prewrap datapre">{JSON.stringify(value, null, 2)}</pre>
              ) : (
                String(value)
              )}
            </div>
          </div>
        ))}
      </div>
      {chat && (
        <div className="transcript">
          {chat.map((message, index) => {
            const said = spoken(message);
            return (
              <div key={index} className="tr-row">
                <span className="tr-at tiny mono">{message.turn ?? index + 1}</span>
                <span className={`tr-who tiny ${said.human ? "tr-user" : "tr-bot"}`}>
                  {said.role}
                </span>
                <span className="tr-text small">{said.text}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
