"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector(".menu-toggle");
    const sidebar = document.querySelector(".sidebar");
    const brand = sidebar.querySelector(".brand");
    const navigation = sidebar.querySelector(".sidebar-nav");
    const page = document.getElementById("contenido");
    const skipLink = document.querySelector(".skip-link");
    const mobile = window.matchMedia("(max-width: 900px)");
    const desktopMenuPreference = "zapateria.menu-collapsed";
    let desktopCollapsed = false;

    try {
        desktopCollapsed = sessionStorage.getItem(desktopMenuPreference) === "true";
    } catch {
        // Storage can be unavailable in a local preview or a private browser.
    }

    function setMenu(open) {
        const returnFocus = !open && (brand.contains(document.activeElement) || navigation.contains(document.activeElement));
        const drawerOpen = mobile.matches && open;
        const label = open ? "Cerrar menú de navegación" : "Abrir menú de navegación";
        document.body.classList.toggle("menu-open", drawerOpen);
        document.body.classList.toggle("menu-collapsed", !mobile.matches && !open);
        toggle.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", label);
        toggle.title = label;
        brand.inert = !open;
        navigation.inert = !open;
        page.inert = drawerOpen;
        skipLink.inert = drawerOpen;
        if (returnFocus) toggle.focus({ preventScroll: true });
    }

    document.body.classList.add("menu-enabled");
    toggle.hidden = false;
    setMenu(!mobile.matches && !desktopCollapsed);
    mobile.addEventListener("change", () => setMenu(!mobile.matches && !desktopCollapsed));
    toggle.addEventListener("click", () => {
        document.body.classList.add("menu-interactive");
        const open = toggle.getAttribute("aria-expanded") !== "true";
        if (!mobile.matches) {
            desktopCollapsed = !open;
            try {
                sessionStorage.setItem(desktopMenuPreference, String(desktopCollapsed));
            } catch {
                // The menu still works without a saved preference.
            }
        }
        setMenu(open);
        if (open) {
            const entry = navigation.querySelector('[aria-current="page"]') ?? navigation.querySelector(".nav-link");
            entry?.focus();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && document.body.classList.contains("menu-open")) {
            setMenu(false);
            toggle.focus({ preventScroll: true });
        }
    });
    sidebar.addEventListener("click", (event) => {
        if (mobile.matches && event.target.closest("a")) setMenu(false);
    });
    document.addEventListener("click", (event) => {
        if (document.body.classList.contains("menu-open") && !sidebar.contains(event.target)) {
            setMenu(false);
        }
    });

    const numbers = new Intl.NumberFormat("es-MX");
    const pesos = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });
    const charts = new Map();

    if (window.Chart) {
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        document.querySelectorAll(".chart-config").forEach((source) => {
            const { labels, values, unit, horizontal } = JSON.parse(source.textContent);
            const canvas = document.getElementById(source.dataset.target);
            const format = unit === "money" ? pesos : numbers;
            const numericAxis = horizontal ? "x" : "y";
            const labelAxis = horizontal ? "y" : "x";

            charts.set(canvas.id, new window.Chart(canvas, {
                type: "bar",
                data: {
                    labels,
                    datasets: [{
                        data: values,
                        backgroundColor: horizontal ? "#0f766e" : ["#0f766e", "#286c96", "#6b5199"],
                        hoverBackgroundColor: horizontal ? "#105c55" : ["#105c55", "#205779", "#56417e"],
                        borderRadius: 6,
                        borderSkipped: false,
                        maxBarThickness: 52
                    }]
                },
                options: {
                    indexAxis: horizontal ? "y" : "x",
                    maintainAspectRatio: false,
                    animation: reduceMotion ? false : { duration: 320, easing: "easeOutQuart" },
                    locale: "es-MX",
                    scales: {
                        [numericAxis]: {
                            beginAtZero: true,
                            border: { display: false },
                            ticks: {
                                color: "#475569",
                                precision: unit === "money" ? undefined : 0,
                                callback: (value) => format.format(value)
                            },
                            grid: { color: "rgba(100, 116, 139, 0.18)" }
                        },
                        [labelAxis]: {
                            border: { display: false },
                            ticks: { color: "#475569" },
                            grid: { display: false }
                        },
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: "#142339",
                            titleColor: "#f8fafc",
                            bodyColor: "#f8fafc",
                            cornerRadius: 8,
                            padding: 10,
                            callbacks: { label: (context) => format.format(context.raw) }
                        }
                    }
                }
            }));
        });
    }

    const picker = document.getElementById("product-picker");
    if (picker) {
        const products = JSON.parse(document.getElementById("stock-data").textContent);
        const valueCells = document.querySelectorAll("[data-stock-value]");
        picker.addEventListener("change", () => {
            const product = products.find((item) => String(item.id) === picker.value);
            const chart = charts.get("chart-comparison");
            if (chart) {
                chart.data.datasets[0].data = product.values;
                chart.update();
            }
            valueCells.forEach((cell, index) => {
                const value = product.values[index];
                cell.textContent = value === null ? "Sin datos" : numbers.format(value);
            });
        });
    }
});
