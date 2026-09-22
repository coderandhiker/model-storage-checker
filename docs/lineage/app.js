(function () {
  "use strict";

  const state = {
    data: null,
    cy: null,
    selectedId: null,
    expanded: new Set(),
  };

  const elements = {
    errorBanner: document.getElementById("error-banner"),
    errorMessage: document.getElementById("error-message"),
    subtitle: document.getElementById("subtitle"),
    summary: document.getElementById("summary"),
    graph: document.getElementById("graph"),
    graphStatus: document.getElementById("graph-status"),
    search: document.getElementById("search"),
    layerFilter: document.getElementById("layer-filter"),
    sessionFilter: document.getElementById("session-filter"),
    expand: document.getElementById("expand-selected"),
    collapse: document.getElementById("collapse-selected"),
    fit: document.getElementById("fit-graph"),
    reset: document.getElementById("reset-graph"),
    breadcrumbs: document.getElementById("breadcrumbs"),
    badges: document.getElementById("selection-badges"),
    selectionSummary: document.getElementById("selection-summary"),
    details: document.getElementById("details"),
  };

  function showError(error) {
    elements.errorMessage.textContent = error instanceof Error ? error.message : String(error);
    elements.errorBanner.hidden = false;
    elements.graphStatus.textContent = "Data unavailable";
  }

  function graphNode(item) {
    return {
      group: "nodes",
      data: {
        ...item,
        provenanceText: item.provenance.join(" · "),
      },
    };
  }

  function graphEdge(item) {
    return {
      group: "edges",
      data: item,
      classes: item.primary ? "primary" : "",
    };
  }

  function addOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.append(option);
  }

  function populateControls(data) {
    data.filters.layers.forEach((item) => {
      addOption(
        elements.layerFilter,
        String(item.layer),
        `Layer ${item.layer}: ${item.name}`,
      );
    });
    data.filters.sessions.forEach((item) => {
      addOption(elements.sessionFilter, item.session_id, item.label);
    });
  }

  function renderSummary(data) {
    const values = [
      ["Sessions", data.summary.logical_sessions],
      ["Attempts", data.summary.process_attempts],
      ["OTel records", data.summary.otel_records],
      ["Spans", data.summary.otel_spans],
      ["Model turns", data.summary.model_turns],
      ["Tool calls", data.summary.tool_calls],
    ];
    elements.summary.replaceChildren();
    values.forEach(([label, value]) => {
      const item = document.createElement("div");
      item.className = "summary-item";
      const strong = document.createElement("strong");
      strong.textContent = Number(value || 0).toLocaleString();
      const span = document.createElement("span");
      span.textContent = label;
      item.append(strong, span);
      elements.summary.append(item);
    });
  }

  function layoutGraph(fit) {
    state.cy
      .layout({
        name: "breadthfirst",
        directed: true,
        roots: "#origin-prompt",
        padding: 36,
        spacingFactor: 1.18,
        animate: false,
        fit,
      })
      .run();
  }

  function initializeGraph(data) {
    const graphElements = [
      ...data.nodes.map(graphNode),
      ...data.edges.map(graphEdge),
    ];
    state.cy = cytoscape({
      container: elements.graph,
      elements: graphElements,
      minZoom: 0.15,
      maxZoom: 2.2,
      wheelSensitivity: 0.18,
      boxSelectionEnabled: false,
      autounselectify: false,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#25c2a0",
            "border-color": "#a9f3df",
            "border-width": 1.5,
            color: "#edf5ff",
            "font-size": 10,
            "font-weight": 700,
            height: 38,
            label: "data(label)",
            "overlay-opacity": 0,
            "text-background-color": "#08111f",
            "text-background-opacity": 0.84,
            "text-background-padding": 4,
            "text-halign": "center",
            "text-margin-y": 29,
            "text-max-width": 132,
            "text-valign": "bottom",
            "text-wrap": "wrap",
            width: 38,
          },
        },
        {
          selector: 'node[kind = "prompt"], node[kind = "session"]',
          style: {
            "background-color": "#8b7cf6",
            "border-color": "#d9d3ff",
            shape: "round-rectangle",
            height: 44,
            width: 56,
          },
        },
        {
          selector:
            'node[kind = "commit"], node[kind = "branch"]',
          style: {
            "background-color": "#ffad5c",
            "border-color": "#ffe0b9",
            shape: "diamond",
          },
        },
        {
          selector:
            'node[kind = "pull-request"], node[kind = "release"]',
          style: {
            "background-color": "#9ba9bc",
            "border-color": "#d8e0eb",
            shape: "hexagon",
          },
        },
        {
          selector: 'node[expandable = true]',
          style: {
            "border-style": "double",
            "border-width": 4,
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-color": "#f9e2af",
            "border-width": 5,
            "overlay-color": "#f9e2af",
            "overlay-opacity": 0.12,
          },
        },
        {
          selector: "node.search-hit",
          style: {
            "border-color": "#66d9ff",
            "border-width": 5,
          },
        },
        {
          selector: ".filtered",
          style: {
            display: "none",
          },
        },
        {
          selector: ".faded",
          style: {
            opacity: 0.16,
          },
        },
        {
          selector: "edge",
          style: {
            "curve-style": "bezier",
            "line-color": "#506987",
            "target-arrow-color": "#506987",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.72,
            width: 1.4,
            label: "data(label)",
            color: "#9fb1c8",
            "font-size": 7,
            "text-background-color": "#08111f",
            "text-background-opacity": 0.84,
            "text-background-padding": 2,
            "text-rotation": "autorotate",
          },
        },
        {
          selector: "edge.primary",
          style: {
            "line-color": "#66d9ff",
            "target-arrow-color": "#66d9ff",
            width: 3,
          },
        },
        {
          selector: "edge:selected",
          style: {
            "line-color": "#f9e2af",
            "target-arrow-color": "#f9e2af",
          },
        },
      ],
    });
    layoutGraph(true);

    state.cy.on("tap", "node", (event) => {
      selectNode(event.target.id());
    });
    state.cy.on("tap", (event) => {
      if (event.target === state.cy) {
        state.cy.elements().unselect();
      }
    });

    let lastTap = { id: null, time: 0 };
    state.cy.on("tap", "node", (event) => {
      const now = Date.now();
      const id = event.target.id();
      if (lastTap.id === id && now - lastTap.time < 420) {
        toggleExpansion(id);
        lastTap = { id: null, time: 0 };
      } else {
        lastTap = { id, time: now };
      }
    });
  }

  function selectNode(id) {
    const selected = state.cy.getElementById(id);
    if (selected.empty()) {
      return;
    }
    state.selectedId = id;
    selected.select();
    renderSelection(selected.data());
    updateButtons();
  }

  function updateButtons() {
    const expansion = state.selectedId
      ? state.data.expansions[state.selectedId]
      : null;
    elements.expand.disabled = !expansion || state.expanded.has(state.selectedId);
    elements.collapse.disabled =
      !expansion || !state.expanded.has(state.selectedId);
  }

  function expandNode(id) {
    const expansion = state.data.expansions[id];
    if (!expansion || state.expanded.has(id)) {
      return;
    }
    const additions = [
      ...expansion.nodes
        .filter((item) => state.cy.getElementById(item.id).empty())
        .map(graphNode),
      ...expansion.edges
        .filter((item) => state.cy.getElementById(item.id).empty())
        .map(graphEdge),
    ];
    state.cy.add(additions);
    state.expanded.add(id);
    applyFilters();
    layoutGraph(false);
    elements.graphStatus.textContent = `Expanded ${state.cy.getElementById(id).data("label")}`;
    updateButtons();
  }

  function collapseNode(id) {
    const expansion = state.data.expansions[id];
    if (!expansion || !state.expanded.has(id)) {
      return;
    }
    expansion.nodes.forEach((item) => {
      const graphItem = state.cy.getElementById(item.id);
      if (!graphItem.empty()) {
        graphItem.remove();
      }
    });
    state.expanded.delete(id);
    if (
      state.selectedId &&
      expansion.nodes.some((item) => item.id === state.selectedId)
    ) {
      selectNode(id);
    }
    layoutGraph(false);
    elements.graphStatus.textContent = `Collapsed ${state.cy.getElementById(id).data("label")}`;
    updateButtons();
  }

  function toggleExpansion(id) {
    if (state.expanded.has(id)) {
      collapseNode(id);
    } else {
      expandNode(id);
    }
  }

  function resetGraph() {
    [...state.expanded].forEach(collapseNode);
    elements.search.value = "";
    elements.layerFilter.value = "";
    elements.sessionFilter.value = "";
    applyFilters();
    layoutGraph(true);
    selectNode("origin-prompt");
    elements.graphStatus.textContent = "Graph reset";
  }

  function applyFilters() {
    if (!state.cy) {
      return;
    }
    const layer = elements.layerFilter.value;
    const session = elements.sessionFilter.value;
    const query = elements.search.value.trim().toLocaleLowerCase();
    state.cy.nodes().forEach((graphNodeItem) => {
      const data = graphNodeItem.data();
      const layerMatch = !layer || String(data.layer || "") === layer;
      const sessionMatch = !session || data.session_id === session;
      graphNodeItem.toggleClass("filtered", !(layerMatch && sessionMatch));
      const searchable = [
        data.id,
        data.label,
        data.kind,
        data.summary,
        data.provenanceText,
      ]
        .join(" ")
        .toLocaleLowerCase();
      const queryMatch = !query || searchable.includes(query);
      graphNodeItem.toggleClass("faded", Boolean(query) && !queryMatch);
      graphNodeItem.toggleClass("search-hit", Boolean(query) && queryMatch);
    });
    state.cy.edges().forEach((graphEdgeItem) => {
      const connectedVisible =
        !graphEdgeItem.source().hasClass("filtered") &&
        !graphEdgeItem.target().hasClass("filtered");
      graphEdgeItem.toggleClass("filtered", !connectedVisible);
      graphEdgeItem.toggleClass(
        "faded",
        graphEdgeItem.source().hasClass("faded") &&
          graphEdgeItem.target().hasClass("faded"),
      );
    });
  }

  function appendBadge(text, className) {
    const badge = document.createElement("span");
    badge.className = `badge ${className || ""}`.trim();
    badge.textContent = text;
    elements.badges.append(badge);
  }

  function renderSelection(data) {
    elements.badges.replaceChildren();
    appendBadge(data.kind, "");
    appendBadge(data.status, `status-${data.status}`);
    (data.provenance || []).forEach((value) => appendBadge(value, ""));
    elements.selectionSummary.textContent =
      data.summary || "No additional summary is available.";
    renderBreadcrumbs(data.id);
    elements.details.replaceChildren();
    const detail = state.data.details[data.id];
    if (detail === undefined) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "No detail payload is available for this node.";
      elements.details.append(empty);
      return;
    }
    elements.details.append(renderValue(detail, "details"));
  }

  function primaryParent(id) {
    const incoming = state.cy
      .getElementById(id)
      .incomers("edge")
      .filter((item) => item.data("primary"));
    const edge = incoming.length ? incoming[0] : state.cy.getElementById(id).incomers("edge")[0];
    return edge ? edge.source().id() : null;
  }

  function renderBreadcrumbs(id) {
    const path = [];
    const seen = new Set();
    let current = id;
    while (current && !seen.has(current) && path.length < 20) {
      seen.add(current);
      path.unshift(current);
      current = primaryParent(current);
    }
    elements.breadcrumbs.replaceChildren();
    path.forEach((nodeId) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const graphItem = state.cy.getElementById(nodeId);
      button.type = "button";
      button.textContent = graphItem.empty() ? nodeId : graphItem.data("label");
      button.addEventListener("click", () => selectNode(nodeId));
      item.append(button);
      elements.breadcrumbs.append(item);
    });
  }

  function scalarText(value) {
    if (value === null) {
      return "null";
    }
    if (typeof value === "string") {
      return value;
    }
    return JSON.stringify(value, null, 2);
  }

  function renderScalar(value) {
    const pre = document.createElement("pre");
    pre.textContent = scalarText(value);
    return pre;
  }

  function renderLazy(group, content, value, label) {
    if (content.dataset.rendered === "true") {
      return;
    }
    content.dataset.rendered = "true";
    content.append(renderValue(value, label));
  }

  function renderValue(value, label) {
    if (value === null || typeof value !== "object") {
      return renderScalar(value);
    }
    if (Array.isArray(value)) {
      const container = document.createElement("div");
      if (!value.length) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "Empty list";
        container.append(empty);
        return container;
      }
      value.forEach((item, index) => {
        const group = document.createElement("details");
        group.className = "detail-group";
        if (index === 0 && value.length <= 4) {
          group.open = true;
        }
        const summary = document.createElement("summary");
        summary.textContent = `${label} ${index + 1} of ${value.length}`;
        const content = document.createElement("div");
        content.className = "detail-group-content";
        group.addEventListener("toggle", () => {
          if (group.open) {
            renderLazy(group, content, item, `${label} item`);
          }
        });
        group.append(summary, content);
        container.append(group);
        if (group.open) {
          renderLazy(group, content, item, `${label} item`);
        }
      });
      return container;
    }

    const list = document.createElement("dl");
    Object.keys(value)
      .sort((left, right) => left.localeCompare(right))
      .forEach((key) => {
        const child = value[key];
        if (child !== null && typeof child === "object") {
          const group = document.createElement("details");
          group.className = "detail-group";
          const summary = document.createElement("summary");
          const size = Array.isArray(child)
            ? ` (${child.length})`
            : ` (${Object.keys(child).length})`;
          summary.textContent = `${key}${size}`;
          const content = document.createElement("div");
          content.className = "detail-group-content";
          group.addEventListener("toggle", () => {
            if (group.open) {
              renderLazy(group, content, child, key);
            }
          });
          group.append(summary, content);
          list.append(group);
          return;
        }
        const row = document.createElement("div");
        row.className = "detail-row";
        const term = document.createElement("dt");
        term.textContent = key;
        const description = document.createElement("dd");
        description.append(renderScalar(child));
        row.append(term, description);
        list.append(row);
      });
    return list;
  }

  function bindControls() {
    elements.expand.addEventListener("click", () => {
      if (state.selectedId) {
        expandNode(state.selectedId);
      }
    });
    elements.collapse.addEventListener("click", () => {
      if (state.selectedId) {
        collapseNode(state.selectedId);
      }
    });
    elements.fit.addEventListener("click", () => {
      state.cy.fit(state.cy.elements().not(".filtered"), 40);
      elements.graphStatus.textContent = "Graph fitted to viewport";
    });
    elements.reset.addEventListener("click", resetGraph);
    elements.search.addEventListener("input", applyFilters);
    elements.layerFilter.addEventListener("change", applyFilters);
    elements.sessionFilter.addEventListener("change", applyFilters);
    elements.graph.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        if (state.selectedId) {
          event.preventDefault();
          expandNode(state.selectedId);
        }
      } else if (event.key === "Escape") {
        if (state.selectedId) {
          collapseNode(state.selectedId);
        }
      } else if (event.key.toLocaleLowerCase() === "f") {
        state.cy.fit(state.cy.elements().not(".filtered"), 40);
      } else if (event.key === "/") {
        event.preventDefault();
        elements.search.focus();
      }
    });
  }

  function pathExists(sourceId, targetId) {
    const adjacency = new Map();
    const allEdges = [
      ...state.data.edges,
      ...Object.values(state.data.expansions).flatMap((item) => item.edges),
    ];
    allEdges.forEach((item) => {
      const targets = adjacency.get(item.source) || [];
      targets.push(item.target);
      adjacency.set(item.source, targets);
    });
    const pending = [sourceId];
    const visited = new Set();
    while (pending.length) {
      const current = pending.shift();
      if (current === targetId) {
        return true;
      }
      if (visited.has(current)) {
        continue;
      }
      visited.add(current);
      (adjacency.get(current) || []).forEach((item) => pending.push(item));
    }
    return false;
  }

  function installValidationApi() {
    Object.defineProperty(window, "__lineageDashboard", {
      configurable: false,
      enumerable: false,
      value: Object.freeze({
        expandNode,
        selectNode,
        snapshot() {
          return {
            selectedId: state.selectedId,
            expanded: [...state.expanded],
            renderedNodes: state.cy.nodes().length,
            renderedEdges: state.cy.edges().length,
            graphStatus: elements.graphStatus.textContent,
          };
        },
        validatePrimaryPath() {
          const parent = state.data.nodes.find(
            (item) =>
              item.kind === "session" && item.label === "Parent orchestrator",
          );
          const child = state.data.nodes.find(
            (item) => item.kind === "session" && item.layer === 1,
          );
          const commit = state.data.nodes.find(
            (item) => item.kind === "commit" && item.layer === 1,
          );
          return {
            parentId: parent && parent.id,
            childId: child && child.id,
            commitId: commit && commit.id,
            parentToChild:
              Boolean(parent && child) && pathExists(parent.id, child.id),
            childToCommit:
              Boolean(child && commit) && pathExists(child.id, commit.id),
          };
        },
      }),
    });
  }

  async function start() {
    if (typeof cytoscape !== "function") {
      throw new Error("The vendored Cytoscape.js library did not load.");
    }
    const response = await fetch("data.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`data.json returned HTTP ${response.status}.`);
    }
    state.data = await response.json();
    elements.subtitle.textContent =
      `${state.data.meta.repository.full_name} · ` +
      `${state.data.summary.commits} stacked commits · ` +
      `${state.data.summary.traces} captured traces`;
    renderSummary(state.data);
    populateControls(state.data);
    initializeGraph(state.data);
    bindControls();
    installValidationApi();
    selectNode("origin-prompt");
    elements.graphStatus.textContent =
      `${state.data.nodes.length} aggregate nodes; ` +
      `${Object.keys(state.data.expansions).length} expandable groups`;
  }

  start().catch(showError);
})();
