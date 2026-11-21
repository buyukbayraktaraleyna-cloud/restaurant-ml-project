// Small helpers for the restaurant rating panel:
//   1. light / dark theme switch (the choice is remembered in the browser)
//   2. tables that can be sorted by clicking a column header
//   3. a text box that filters the rows of a table while you type
//   4. filter forms that are sent automatically when a field changes
(function () {
  "use strict";

  var root = document.documentElement;

  // ---------------------------------------------------------------------
  // 1. Theme: apply the saved choice right away so the page does not flash
  // ---------------------------------------------------------------------
  try {
    var saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      root.setAttribute("data-theme", saved);
    }
  } catch (error) {
    // localStorage can be blocked, the system theme is used then
  }

  function currentTheme() {
    var chosen = root.getAttribute("data-theme");
    if (chosen) {
      return chosen;
    }
    var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
  }

  function setupThemeButton() {
    var button = document.getElementById("theme-toggle");
    if (!button) {
      return;
    }
    function updateLabel() {
      // The icon shows the theme you get when you click the button
      button.textContent = currentTheme() === "dark" ? "\u2600" : "\u263E";
    }
    button.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (error) {
        // ignore, the choice just will not be remembered
      }
      updateLabel();
    });
    updateLabel();
  }

  // ---------------------------------------------------------------------
  // 2. Sortable tables: <table class="sortable"> with a <thead> and a <tbody>
  // ---------------------------------------------------------------------
  var NUMBER_PATTERN = /^-?\d+(\.\d+)?\s*(%|s)?$/;

  function readCell(cell) {
    var text = cell.textContent.trim();
    if (text === "" || text === "-") {
      return { missing: true, number: null, text: "" };
    }
    var number = NUMBER_PATTERN.test(text) ? parseFloat(text) : null;
    return { missing: false, number: number, text: text.toLowerCase() };
  }

  function sortTable(table, column, ascending) {
    var body = table.tBodies[0];
    var rows = Array.prototype.slice.call(body.rows);

    rows.sort(function (rowA, rowB) {
      var a = readCell(rowA.cells[column]);
      var b = readCell(rowB.cells[column]);
      // Rows without a value always go to the bottom
      if (a.missing || b.missing) {
        return a.missing === b.missing ? 0 : (a.missing ? 1 : -1);
      }
      var result;
      if (a.number !== null && b.number !== null) {
        result = a.number - b.number;
      } else {
        result = a.text.localeCompare(b.text);
      }
      return ascending ? result : -result;
    });

    rows.forEach(function (row) {
      body.appendChild(row);
    });
  }

  function setupSortableTables() {
    var tables = document.querySelectorAll("table.sortable");
    Array.prototype.forEach.call(tables, function (table) {
      if (!table.tHead || !table.tBodies.length) {
        return;
      }
      var headers = table.tHead.rows[0].cells;
      Array.prototype.forEach.call(headers, function (header, column) {
        header.setAttribute("data-sortable", "true");
        header.setAttribute("title", "Click to sort");
        header.addEventListener("click", function () {
          var ascending = header.getAttribute("data-sort") !== "asc";
          Array.prototype.forEach.call(headers, function (other) {
            other.removeAttribute("data-sort");
          });
          header.setAttribute("data-sort", ascending ? "asc" : "desc");
          sortTable(table, column, ascending);
        });
      });
    });
  }

  // ---------------------------------------------------------------------
  // 3. Table filter: <input data-filter-table="#table-id">
  // ---------------------------------------------------------------------
  function setupTableFilters() {
    var inputs = document.querySelectorAll("input[data-filter-table]");
    Array.prototype.forEach.call(inputs, function (input) {
      var table = document.querySelector(input.getAttribute("data-filter-table"));
      if (!table || !table.tBodies.length) {
        return;
      }
      input.addEventListener("input", function () {
        var term = input.value.trim().toLowerCase();
        Array.prototype.forEach.call(table.tBodies[0].rows, function (row) {
          row.hidden = term !== "" && row.textContent.toLowerCase().indexOf(term) === -1;
        });
      });
    });
  }

  // ---------------------------------------------------------------------
  // 4. Auto-submit: <form data-autosubmit> is sent when a select or a checkbox changes
  // ---------------------------------------------------------------------
  function setupAutoSubmit() {
    var fields = document.querySelectorAll(
      "form[data-autosubmit] select, form[data-autosubmit] input[type=checkbox]"
    );
    Array.prototype.forEach.call(fields, function (field) {
      field.addEventListener("change", function () {
        field.form.submit();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupThemeButton();
    setupSortableTables();
    setupTableFilters();
    setupAutoSubmit();
  });
})();
