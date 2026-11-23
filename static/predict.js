// Predict page: shows the currency and the typical cost of the chosen country
// next to the cost field, so the visitor knows in which money to type the cost.
(function () {
  "use strict";

  var select = document.getElementById("country");
  var hint = document.getElementById("cost-hint");
  var dataTag = document.getElementById("country-info");
  if (!select || !hint || !dataTag) {
    return;
  }

  var info = {};
  try {
    info = JSON.parse(dataTag.textContent);
  } catch (error) {
    return;
  }

  function update() {
    var country = info[select.value];
    if (!country) {
      hint.textContent = "";
      return;
    }
    hint.textContent = hint.dataset.currency + ": " + country.currency +
      " · " + hint.dataset.typical + ": " + country.median;
  }

  select.addEventListener("change", update);
  update();
})();
