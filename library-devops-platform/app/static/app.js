const $ = (id) => document.getElementById(id);
const numeric = ["copies", "book_id", "member_id"];

async function loadBooks() {
  const response = await fetch("/api/books?q=" + encodeURIComponent($("search").value));
  if (!response.ok) return;
  $("books").replaceChildren(...(await response.json()).map((book) => {
    const row = document.createElement("tr");
    [book.id, book.title, book.author, book.isbn,
     `${book.available_copies} / ${book.total_copies}`].forEach((value) => {
      row.insertCell().textContent = value;  // textContent prevents script injection
    });
    return row;
  }));
}

async function send(url, payload, form) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": $("key").value },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  $("message").textContent = response.ok ? `Saved (ID ${result.id})` : result.error;
  if (response.ok) { form.reset(); loadBooks(); }
}

document.querySelectorAll("form").forEach((form) => form.addEventListener("submit", (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  if (form.id === "return") return send(`/api/loans/${Number(data.loan_id)}/return`, {}, form);
  numeric.forEach((key) => { if (key in data) data[key] = Number(data[key]); });
  send(form.dataset.url, data, form);
}));

$("search").addEventListener("input", loadBooks);
loadBooks();
