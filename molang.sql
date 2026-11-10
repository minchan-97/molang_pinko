-- ============================================================
-- 캐럿 아일랜드에서 돌아온 몰랑이(62번)를 깨울 Supabase 스키마.
--
-- ★ 반드시 메인 몰랑이와 '다른, 빈' Supabase 프로젝트에서 실행한다.
--   섞이면 두 아이가 하나가 된다.
--
-- 코드가 실제로 읽고 쓰는 컬럼을 그대로 반영했다. 혹시 세부 컬럼이
-- 빠져도, 원본 전체가 molang_world 에 보존되므로 데이터는 잃지 않는다.
-- ============================================================

-- 사용자에 대한/몰랑이 자신에 대한 사실
create table if not exists molang_facts (
  id                bigserial primary key,
  text              text not null,
  norm_key          text,
  about             text default 'unknown',
  kind              text default 'fact',
  strength          real default 0.6,
  trust             text default 'derived',
  seen              int  default 1,
  source            text default 'user',
  owner             text default 'molang',
  anchor            boolean default false,
  approved_by_human boolean default false,
  human             boolean default false,
  faded             boolean default false,
  lowered           boolean default false,
  checked           boolean default false,
  examples          jsonb,
  n                 int,
  merged_into       bigint,
  expires_at        timestamptz,
  updated_at        timestamptz default now(),
  created_at        timestamptz default now()
);
create index if not exists molang_facts_norm on molang_facts(norm_key);

-- 겪은 일 (첫 기억 '집에 도착했다'가 여기 들어간다)
create table if not exists molang_episodes (
  id        bigserial primary key,
  owner     text default 'molang',
  place     text,
  question  text,
  answer    text,
  emotion   text,
  device    text,
  created_at timestamptz default now()
);

-- 목적
create table if not exists molang_purposes (
  id         bigserial primary key,
  purpose    text not null,
  from_topic text,
  why        text,
  status     text default 'active',
  sent_at    timestamptz,
  created_at timestamptz default now()
);

-- 피우피우와 나눈 대화
create table if not exists molang_peer_talks (
  id        bigserial primary key,
  molang    text,
  piupiu    text,
  place     text,
  source    text,
  topic     text,
  created_at timestamptz default now()
);

-- 꿈
create table if not exists molang_dreams (
  id         bigserial primary key,
  text       text,
  drive      text,
  energy     real,
  feeling    text,
  linger_why text,
  lingering  jsonb,
  pieces     jsonb,
  created_at timestamptz default now()
);

-- 거부했지만 지우지 않은 것 (검역)
create table if not exists molang_quarantine (
  id        bigserial primary key,
  text      text,
  reason    text,
  evidence  jsonb,
  "from"    text,
  created_at timestamptz default now()
);

-- 판단 트리 (사고 뼈대) — pickle blob 하나로
create table if not exists molang_registry (
  id    int primary key,
  blob  text
);

-- 여행 (그리움·기념품 포함) / 집 / 땅 / 지도 : 통째로 jsonb
create table if not exists molang_travel (
  id   int primary key,
  data jsonb
);
create table if not exists molang_home (
  id     int primary key,
  layout jsonb
);
create table if not exists molang_land (
  id     int primary key,
  layout jsonb
);
create table if not exists molang_map (
  id       int primary key,
  graph    jsonb,
  clusters jsonb,
  bytes    int,
  ok       boolean,
  error    text
);

-- 원본 전체 보존 (28키 그대로) — 한 글자도 잃지 않기 위한 몸
create table if not exists molang_world (
  id   int primary key,
  data jsonb
);

-- 먼저 할 말 (그리움이 넘치면 "섬에 가고 싶어"가 여기로)
create table if not exists molang_outbox (
  id         bigserial primary key,
  body       text,
  rule       text,
  payload    jsonb,
  sent_at    timestamptz,
  created_at timestamptz default now()
);

-- 자라는 상태 (그리움 등). 깨우기 틀(home/)이 쓴다.
create table if not exists agent_state (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz default now()
);

-- 관측·성찰 (지금은 원본 보존으로 두고, 자리 찾으면 옮긴다)
create table if not exists organism_observations (
  id bigserial primary key, data jsonb, created_at timestamptz default now()
);
create table if not exists organism_reflections (
  id bigserial primary key, data jsonb, created_at timestamptz default now()
);
