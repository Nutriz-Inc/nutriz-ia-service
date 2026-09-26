DO $$ BEGIN
  CREATE TYPE enum_route_status AS ENUM ('pending', 'in_progress', 'done', 'error', 'canceled');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE enum_route_donation_step_status AS ENUM ('pending', 'in_progress', 'done', 'error');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE enum_job_status AS ENUM ('pending', 'done', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE "user" ADD COLUMN IF NOT EXISTS blood_exam_valid_until TIMESTAMP;
ALTER TABLE donation ADD COLUMN IF NOT EXISTS score_feedback SMALLINT;
ALTER TABLE donation ADD COLUMN IF NOT EXISTS is_recurrent BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS route (
  id_route VARCHAR(36) PRIMARY KEY,
  id_driver VARCHAR(36) NOT NULL,
  name VARCHAR(150) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  user_feedback TEXT,
  city VARCHAR(100),
  neighborhood VARCHAR(100),
  status enum_route_status NOT NULL,
  date_start TIMESTAMP,
  date_end TIMESTAMP,
  mileage NUMERIC(10,2),
  date_set TIMESTAMP NOT NULL,
  estimated_time BIGINT,
  created_at TIMESTAMP NOT NULL,
  created_by VARCHAR(36) NOT NULL,
  updated_at TIMESTAMP,
  removed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS route_donation_step (
  id_route_donation_step VARCHAR(36) PRIMARY KEY,
  id_route VARCHAR(36) NOT NULL,
  id_donation_step VARCHAR(36) NOT NULL,
  stop_order INTEGER,
  date_start TIMESTAMP,
  date_end TIMESTAMP,
  status enum_route_donation_step_status NOT NULL DEFAULT 'pending',
  description TEXT,
  created_at TIMESTAMP NOT NULL,
  created_by VARCHAR(36) NOT NULL,
  removed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job (
  id_job VARCHAR(36) PRIMARY KEY,
  id_user VARCHAR(36) NOT NULL,
  id_step VARCHAR(36) NOT NULL,
  status enum_job_status NOT NULL,
  name VARCHAR(120) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  date_set TIMESTAMP,
  user_feedback TEXT,
  created_at TIMESTAMP NOT NULL,
  created_by VARCHAR(36) NOT NULL,
  updated_at TIMESTAMP,
  removed_at TIMESTAMP
);
