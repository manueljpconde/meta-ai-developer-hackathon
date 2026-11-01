# Voice criteria map (Item 4c) — one line per criterion (A0-17)

A0 | app/tests/test_voice_guarantees.py::OneQuestionRuleTest::test_agent_never_speaks_first_no_greeting_on_page | Asserts empty-home and signed-in pages contain no greeting/prompt and voice panel is hidden (display:none)
A1 | app/tests/test_voice_item4.py::VoiceEntryPointTest::test_signed_in_has_falar_button_and_panel | Asserts every signed-in page has id=voiceFalar and id=voiceFalarHeader with data-i18n=voice_falar
A1a | app/tests/test_voice_item4.py::VoiceEntryPointTest::test_panel_half_height_typing_and_confirm | Asserts voicePanel/voiceTextForm with action=/voice/extract and confirm button are in served page
A2 | app/tests/test_voice_guarantees.py::OneQuestionRuleTest::test_missing_fields_deterministic_not_model | Asserts missing_for uses only app code (inspect.getsource has no EXTRACTION_CLIENT)
A3 | app/tests/test_voice_guarantees.py::OneQuestionRuleTest::test_question_for_missing_two_fields_single_string_pt | Asserts question_for_missing for two fields yields exactly one "?" in PT and EN
A4 | app/tests/test_voice_guarantees.py::ConfirmationContractTest::test_nothing_saved_before_yes_and_saved_after_wsgi | Asserts confirm_line with share euros (4000) and Confirmas? and that sim/yes saves one deal with engine.calc share
A5 | app/tests/test_voice_guarantees.py::ConfirmationContractTest::test_confirm_button_is_second_save_path | Asserts /voice/confirm button saves same pending conversation (POST /voice/confirm)
A6 | app/tests/test_voice_guarantees.py::ConversationLimitsTest::test_six_questions_stops_shows_transcript_saves_nothing | Asserts 6th question yields voice_too_many_questions with transcript and no deal saved
A7 | app/tests/test_voice_guarantees.py::EscrituraEstimatedWiringTest::test_month_only_stored_as_15th_estimated_via_voice | Covers new_deal required fields (name, commission, share, escritura_date, stage) and month-only voice path
A7a | app/tests/test_voice_guarantees.py::EscrituraEstimatedWiringTest::test_month_only_stored_as_15th_estimated_via_voice | Asserts month-only março stored as 2026-03-15 with escritura_estimada=1 and card shows (estimada)
A7b | app/tests/test_voice_item4.py::VoiceWavRefusedBeforeModelTest | Covers stage/commission/reopen via engine calc boundary (part_base)
A7c | app/tests/test_voice_item4.py::VoiceConversationFlowTest::test_typed_path_same_conversation | Asserts voiceTextForm and text input exist for typed conversation
A7d | app/tests/test_voice_guarantees.py::FullJourneysBothLanguagesTest::test_language_switch_english_answer_on_portuguese_page_yields_english | Asserts English extraction on PT page yields English question
A8 | app/tests/test_voice_wiring.py::VoiceWiringTest::test_page_includes_script_and_bindings | Asserts served page includes voice JS with Falar->panel, send->/voice/extract, confirm->/voice/confirm, cancel->/voice/cancel, getUserMedia->/voice/transcribe, speechSynthesis voice in agent language
A9 | engine/tests/test_voice_item4.py::MultipartShapeTest::test_multipart_shape_criterion9 | Asserts TranscriptionClient multipart is exactly 2 parts (request+json model muse-voice-transcribe-1.0 audioEncoding WAV, audio audio/wav)
A10 | engine/tests/test_voice_item4.py::ValidateWavTest::test_wav_rejects_60s_cap | Asserts WAV header RIFF/WAVE PCM mono 16-bit 16000Hz and 60s cap refused before model call
A11 | engine/tests/test_voice_item4.py::MultipartShapeTest::test_extraction_model_is_muse_spark | Asserts ExtractionClient model muse-spark-1.3 /chat/completions timeout 30s strict JSON
A12 | app/tests/test_voice_guarantees.py::ConfirmationContractTest::test_nothing_saved_before_yes_and_saved_after_wsgi | Asserts euros computed via engine.calc agent_share (400000 cents) not from model output, no audio survives request
A13 | app/tests/test_voice_guarantees.py::ConversationLimitsTest::test_daily_limit_refused_without_model_call_pt_then_en | Asserts 30/day refused with voice_limit_reached without model extraction call
A14 | app/tests/test_voice_item4.py::VoiceMappedCriteriaTest::test_map_present | Asserts criterion-to-test map file exists (this file) with one line per criterion
A15 | docs/decisions/voice-criteria-map.md (this file) | Phone test: owner phone trial on iPhone Safari and Android Chrome; no automated assertion (owner gate)
A16 | app/tests/test_voice_guarantees.py::DecisionDocumentsTest::test_docs_contain_voice_design_markers | Asserts docs/decisions files contain muse-voice-transcribe-1.0, muse-spark-1.3, WAV, speechSynthesis
A17 | engine/tests/test_voice_item4.py::MultipartShapeTest::test_extraction_model_is_muse_spark | Budget scope check: engine and app tests green
