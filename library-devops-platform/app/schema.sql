-- Idempotent schema. Keep changes backward compatible (add, do not rename or drop),
-- because old and new application versions run side by side during a canary.
CREATE TABLE IF NOT EXISTS books (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    isbn             TEXT NOT NULL UNIQUE,
    title            TEXT NOT NULL,
    author           TEXT NOT NULL,
    total_copies     INTEGER NOT NULL CHECK (total_copies >= 0),
    available_copies INTEGER NOT NULL
        CHECK (available_copies >= 0 AND available_copies <= total_copies)
);

CREATE TABLE IF NOT EXISTS members (
    id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS loans (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    book_id     BIGINT NOT NULL REFERENCES books (id),
    member_id   BIGINT NOT NULL REFERENCES members (id),
    loaned_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    due_at      TIMESTAMPTZ NOT NULL,
    returned_at TIMESTAMPTZ
);

-- A member can hold only one active loan of the same book.
CREATE UNIQUE INDEX IF NOT EXISTS one_active_loan
    ON loans (book_id, member_id) WHERE returned_at IS NULL;
