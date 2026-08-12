-- ============================================================
-- LMS Core schema — Module: Course Management
-- Namespaced with lms_ prefix so it can live in the same shared
-- ats.db alongside ATS tables (per contracts/README.md convention:
-- "Shared data contracts between modules. All teams read and write here.")
-- ============================================================

CREATE TABLE IF NOT EXISTS lms_programs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,              -- vd: "NextGen 2026", "AI in Action"
  description TEXT,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lms_courses (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  program_id  INTEGER NOT NULL REFERENCES lms_programs(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  description TEXT,
  order_index INTEGER DEFAULT 0,
  owner_id    INTEGER REFERENCES lms_users(id) ON DELETE SET NULL,  -- instructor owner; NULL = admin-managed
  due_date    TEXT,                                                  -- ISO date 'YYYY-MM-DD' hoặc NULL nếu không có deadline
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lms_lessons (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  course_id    INTEGER NOT NULL REFERENCES lms_courses(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  content_type TEXT NOT NULL DEFAULT 'text',   -- 'video' | 'pdf' | 'text' | 'quiz'
  content_url  TEXT,                            -- link Drive/YouTube, hoặc để trống nếu là text/quiz
  content_body TEXT,                             -- dùng cho content_type='text' hoặc mô tả quiz
  order_index  INTEGER DEFAULT 0,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Bảng dưới đây thuộc phạm vi Enrollment/Progress (sprint sau) —
-- tạo sẵn vì Course Management cần biết course có bao nhiêu learner
-- để hiển thị đếm trên dashboard, nhưng CHƯA build route ở bước này.
CREATE TABLE IF NOT EXISTS lms_users (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  email  TEXT UNIQUE NOT NULL,
  name   TEXT NOT NULL,
  role   TEXT NOT NULL DEFAULT 'learner'   -- 'learner' | 'instructor' | 'admin'
);

CREATE TABLE IF NOT EXISTS lms_enrollments (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES lms_users(id) ON DELETE CASCADE,
  course_id    INTEGER NOT NULL REFERENCES lms_courses(id) ON DELETE CASCADE,
  status       TEXT DEFAULT 'in_progress',   -- 'in_progress' | 'completed'
  progress_pct INTEGER DEFAULT 0,
  enrolled_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  UNIQUE(user_id, course_id)
);

CREATE TABLE IF NOT EXISTS lms_lesson_progress (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  enrollment_id INTEGER NOT NULL REFERENCES lms_enrollments(id) ON DELETE CASCADE,
  lesson_id     INTEGER NOT NULL REFERENCES lms_lessons(id) ON DELETE CASCADE,
  status        TEXT DEFAULT 'not_started',  -- 'not_started' | 'done'
  score         INTEGER,                      -- chỉ dùng khi content_type='quiz'
  UNIQUE(enrollment_id, lesson_id)
);

-- Nhiều câu hỏi cho 1 lesson quiz. Ngoài các quiz cũ đã lưu chuỗi pipe
-- trong lms_lessons.content_body — init_lms_db() sẽ migrate lazily sang đây.
CREATE TABLE IF NOT EXISTS lms_quiz_questions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  lesson_id      INTEGER NOT NULL REFERENCES lms_lessons(id) ON DELETE CASCADE,
  question_text  TEXT NOT NULL,
  correct_answer TEXT NOT NULL,
  wrong_choices  TEXT NOT NULL DEFAULT '',   -- pipe-separated: "A | B | C"
  order_index    INTEGER DEFAULT 0
);

-- Index phục vụ query dashboard (đếm learner theo course, progress trung bình)
CREATE INDEX IF NOT EXISTS idx_lms_courses_program ON lms_courses(program_id);
CREATE INDEX IF NOT EXISTS idx_lms_courses_owner ON lms_courses(owner_id);
CREATE INDEX IF NOT EXISTS idx_lms_lessons_course ON lms_lessons(course_id);
CREATE INDEX IF NOT EXISTS idx_lms_enrollments_course ON lms_enrollments(course_id);
CREATE INDEX IF NOT EXISTS idx_lms_quiz_questions_lesson ON lms_quiz_questions(lesson_id);
