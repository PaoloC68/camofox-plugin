/**
 * Initialize the draggable/resizable floating panel.
 * Called once when the panel element is first available in the DOM.
 */
export function initPanel(panelEl) {
    const titleBar = panelEl.querySelector(".camofox-title-bar");
    if (!titleBar) return;
    if (panelEl._camofoxInitialized) return; // prevent double-init
    panelEl._camofoxInitialized = true;

    let isDragging = false;
    let dragStartX = 0, dragStartY = 0, panelStartX = 0, panelStartY = 0;

    const store = Alpine.store("camofox");

    // Set explicit size first
    const w = store.panelSize.w || 800;
    const h = store.panelSize.h || 600;
    panelEl.style.width = w + "px";
    panelEl.style.height = h + "px";

    // Position: use saved position or default to top-right area
    if (store.panelPosition.x !== null && store.panelPosition.y !== null) {
        panelEl.style.left = store.panelPosition.x + "px";
        panelEl.style.top = store.panelPosition.y + "px";
    } else {
        // Default: right side, vertically centered
        const defaultX = Math.max(20, window.innerWidth - w - 40);
        const defaultY = Math.max(60, Math.floor((window.innerHeight - h) / 2));
        panelEl.style.left = defaultX + "px";
        panelEl.style.top = defaultY + "px";
    }
    // Clear any right/bottom that might conflict
    panelEl.style.right = "auto";
    panelEl.style.bottom = "auto";

    // Drag: mousedown on title bar
    titleBar.addEventListener("mousedown", (e) => {
        if (e.target.closest(".camofox-controls")) return;
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        const rect = panelEl.getBoundingClientRect();
        panelStartX = rect.left;
        panelStartY = rect.top;
        titleBar.style.cursor = "grabbing";
        e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        let newX = panelStartX + (e.clientX - dragStartX);
        let newY = panelStartY + (e.clientY - dragStartY);
        newX = Math.max(0, Math.min(newX, window.innerWidth - 100));
        newY = Math.max(0, Math.min(newY, window.innerHeight - 40));
        panelEl.style.left = newX + "px";
        panelEl.style.top = newY + "px";
    });

    document.addEventListener("mouseup", () => {
        if (!isDragging) return;
        isDragging = false;
        titleBar.style.cursor = "grab";
        const rect = panelEl.getBoundingClientRect();
        store.savePosition(rect.left, rect.top);
    });

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
        if (!isDragging) {
            store.saveSize(panelEl.offsetWidth, panelEl.offsetHeight);
        }
    });
    resizeObserver.observe(panelEl);

    // Keep in viewport on window resize
    window.addEventListener("resize", () => {
        const rect = panelEl.getBoundingClientRect();
        if (rect.left > window.innerWidth - 100) {
            panelEl.style.left = Math.max(0, window.innerWidth - panelEl.offsetWidth - 20) + "px";
        }
        if (rect.top > window.innerHeight - 40) {
            panelEl.style.top = Math.max(0, window.innerHeight - panelEl.offsetHeight - 20) + "px";
        }
    });
}
