-- DA-16: отдельная причина переноса «цепочка зависимостей выводит старт за конец квартала».
INSERT INTO ref_decision_reasons (code, ord, decision, label, legacy_reason) VALUES
  ('GRAPH_HORIZON', 11, 'deferred_next_pi', 'Цепочка зависимостей выводит старт за конец квартала', 'M3')
ON CONFLICT (code) DO UPDATE SET ord = EXCLUDED.ord, decision = EXCLUDED.decision,
    label = EXCLUDED.label, legacy_reason = EXCLUDED.legacy_reason;
