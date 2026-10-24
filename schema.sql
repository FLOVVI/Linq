-- schema.sql
CREATE TYPE violation_type AS ENUM ('RUNNING','DANGER_PROXIMITY','PHONE_USAGE','SMOKING_FIRE','FENCE_CLIMBING','NO_HARNESS_HEIGHT','PERSON_FALL','CARGO_VIOLATION',
  'NO_HELMET','NO_VEST','DANGER_ZONE','NO_GLOVES','NO_GOGGLES');  -- 09–13: СИЗ и опасная зона (ИИ-модуль)
CREATE TYPE event_status AS ENUM ('new','sent_to_master','confirmed','false_alarm');
CREATE TYPE severity_type AS ENUM ('critical','warning');
CREATE TYPE camera_kind AS ENUM ('static','dynamic');

CREATE TABLE roles (
    id int PRIMARY KEY, 
    name varchar UNIQUE NOT NULL
);

CREATE TABLE users (
    id serial PRIMARY KEY,
    login varchar UNIQUE NOT NULL,
    password_hash text NOT NULL,
    role_id int NOT NULL REFERENCES roles(id),
    full_name varchar NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    token text PRIMARY KEY, 
    user_id int NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz DEFAULT now(),
    expires_at timestamptz
);

CREATE TABLE sites (
    id serial PRIMARY KEY,
    name varchar UNIQUE NOT NULL,
    rules jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE cameras (
   id serial PRIMARY KEY,
   code varchar,
   site_id int NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
   name varchar NOT NULL,
   camera_type camera_kind NOT NULL DEFAULT 'dynamic',
   pan_angle real NOT NULL DEFAULT 0,
   zoom_level real NOT NULL DEFAULT 1,
   auto_patrol boolean NOT NULL DEFAULT false,
   rtsp_url varchar,
   is_active boolean NOT NULL DEFAULT true,
   rules_vector jsonb NOT NULL,
   map_pos jsonb,
   zones jsonb NOT NULL DEFAULT '[]',
   extra jsonb NOT NULL DEFAULT '{}',   -- tiltAngle, tpuProgram, workers (поля интерфейса без своих колонок)
   created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE events (
    id serial PRIMARY KEY,
    camera_id int NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    violation violation_type NOT NULL,
    severity severity_type NOT NULL DEFAULT 'warning',
    frame_url text, 
    ai_map_url text,
    ai_pos jsonb,
    status event_status NOT NULL DEFAULT 'new',
    processed_by_id int REFERENCES users(id),
    processed_at timestamptz,
    confidence real,
    description text,
    timestamp timestamptz NOT NULL DEFAULT now(),   -- начало нарушения
    ended_at timestamptz,                           -- конец нарушения (ИИ присылает по завершении)
    duration_s real,
    clip_url text,                                  -- видеоклип нарушения
    zone text,                                      -- зоны, где оно произошло
    ai_event_id text UNIQUE,                        -- id события в ИИ-модуле
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_events_cam_id ON events(camera_id, id DESC);
CREATE INDEX ix_events_status ON events(status, id DESC);
CREATE INDEX ix_events_ts ON events(timestamp);

CREATE TABLE settings (
    key varchar PRIMARY KEY, 
    value jsonb NOT NULL
);