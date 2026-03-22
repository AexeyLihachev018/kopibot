import json
from agents.dispatcher import Dispatcher
from agents.style_analyst import StyleAnalyst
from agents.researcher import Researcher
from agents.generator import Generator
from agents.editor import Editor
from agents.critic import Critic
from agents.content_planner import ContentPlanner
from tools.style_store import load_style_guide, save_style_guide, style_guide_summary
from tools.plan_store import load_plan, save_plan, mark_done
from tools.file_parser import parse_file


class Orchestrator:
    def __init__(self):
        self.dispatcher = Dispatcher()
        self.style_analyst = StyleAnalyst()
        self.researcher = Researcher()
        self.generator = Generator()
        self.editor = Editor()
        self.critic = Critic()
        self.planner = ContentPlanner()

    async def handle_message(self, text: str) -> str:
        """Route plain text message through agents."""
        intent_data = await self.dispatcher.classify(text)
        intent = intent_data.get("intent", "unknown")
        style_guide = load_style_guide()

        if intent == "generate_post":
            topic = intent_data.get("topic") or text
            return await self._generate_flow(topic, style_guide)

        elif intent == "edit_post":
            post_text = intent_data.get("text") or text
            command = intent_data.get("command") or "humanize"
            return await self.editor.edit(post_text, command, style_guide)

        elif intent == "create_plan":
            plan = await self.planner.create_plan(
                "месяц", topic=text, style_guide=style_guide
            )
            save_plan(plan)
            return await self.planner.format_plan_message(plan)

        elif intent == "generate_from_plan":
            plan = load_plan()
            next_item = await self.planner.get_next(plan)
            if not next_item:
                return "Контент-план пуст или все посты готовы."
            return await self._generate_flow(next_item["topic"], style_guide)

        elif intent == "show_plan":
            plan = load_plan()
            if not plan:
                return "Контент-план пуст. Загрузи файл или попроси создать план."
            return await self.planner.format_plan_message(plan)

        elif intent == "next_post":
            plan = load_plan()
            next_item = await self.planner.get_next(plan)
            if not next_item:
                return "В плане нет следующего поста."
            return (
                f"Следующий пост:\n\n*{next_item['topic']}*\n\n"
                f"Напиши 'пиши этот пост' чтобы сгенерировать."
            )

        elif intent == "plan_done":
            plan_id = intent_data.get("plan_id")
            if plan_id:
                plan = load_plan()
                plan = mark_done(plan, plan_id)
                save_plan(plan)
                return f"Пост {plan_id} отмечен как опубликованный."
            return "Укажи ID поста: например 'готово 001'"

        elif intent == "analyze_style":
            sg = load_style_guide()
            if not sg:
                return (
                    "Стилевой профиль ещё не создан. "
                    "Загрузи архив постов (MD или JSON)."
                )
            return (
                f"Текущий стилевой профиль:\n\n"
                f"```json\n{json.dumps(sg, ensure_ascii=False, indent=2)}\n```"
            )

        elif intent == "critique":
            post_text = intent_data.get("text") or text
            result = await self.critic.critique(post_text, style_guide)
            return self._format_critique(result)

        elif intent == "research":
            topic = intent_data.get("topic") or text
            brief = await self.researcher.research(topic, style_guide=style_guide)
            return brief

        else:
            return (
                "Не понял запрос. Вот что я умею:\n\n"
                "• Написать пост — *напиши пост о [теме]*\n"
                "• Отредактировать — вставь текст + команда (короче, хлестче, живее...)\n"
                "• Оценить текст — *оцени этот пост: [текст]*\n"
                "• Контент-план — *создай план на месяц*\n"
                "• Показать план — *покажи план*\n"
                "• Загрузить архив — прикрепи .md или .json файл"
            )

    async def handle_file(self, filename: str, content: str) -> str:
        """Handle uploaded file."""
        texts = parse_file(filename, content)
        if not texts:
            return (
                f"Не удалось извлечь тексты из файла {filename}. "
                f"Убедись что это экспорт Telegram (MD или JSON)."
            )

        # Try to detect if it's a content plan
        if "plan" in filename.lower() or "план" in filename.lower():
            combined = "\n\n".join(texts)
            plan = await self.planner.parse_plan(combined)
            save_plan(plan)
            return (
                f"Контент-план загружен: {len(plan)} постов.\n\n"
                + await self.planner.format_plan_message(plan)
            )

        # Treat as style archive
        style_guide = await self.style_analyst.analyze(texts[:50])  # limit to 50 posts
        save_style_guide(style_guide)
        return (
            f"✅ Архив обработан: {len(texts)} постов проанализировано.\n\n"
            f"*Стилевой профиль сохранён:*\n"
            f"🎭 Тон: {style_guide.get('tone', '—')}\n"
            f"🎵 Ритм: {style_guide.get('sentence_rhythm', '—')}\n"
            f"📏 Средняя длина поста: {style_guide.get('avg_post_length', '—')} симв.\n"
            f"😊 Эмодзи: {style_guide.get('emoji_usage', '—')}\n\n"
            f"✍️ Теперь буду писать в твоём стиле."
        )

    async def _generate_flow(self, topic: str, style_guide: dict) -> str:
        """Research -> Generate -> Critique flow."""
        brief = await self.researcher.research(topic, style_guide=style_guide)
        post = await self.generator.generate(
            topic, brief=brief, style_guide=style_guide
        )
        critique = await self.critic.critique(post, style_guide)

        if critique["decision"] == "rewrite":
            post = await self.generator.generate(
                topic, brief=brief, style_guide=style_guide
            )
            critique = await self.critic.critique(post, style_guide)
        elif critique["decision"] == "revise" and critique.get("edit_commands"):
            for cmd in critique["edit_commands"][:2]:
                edited = await self.editor.edit(post, cmd, style_guide)
                # Extract just the РЕЗУЛЬТАТ section if present
                if "РЕЗУЛЬТАТ:" in edited:
                    parts = edited.split("РЕЗУЛЬТАТ:")
                    if len(parts) > 1:
                        result_part = parts[1]
                        # Strip the ПРАВКИ section if present
                        if "ПРАВКИ:" in result_part:
                            result_part = result_part.split("ПРАВКИ:")[0]
                        post = result_part.strip()
                else:
                    post = edited

        score = critique.get("score", "—")
        return f"{post}\n\n— — —\n_Оценка Критика: {score}/10_"

    def _format_critique(self, result: dict) -> str:
        score = result.get("score", "—")
        breakdown = result.get("breakdown", {})
        issues = result.get("issues", [])
        decision_map = {
            "publish": "публиковать",
            "revise": "доработать",
            "rewrite": "переписать",
        }
        decision = decision_map.get(
            result.get("decision", ""), result.get("decision", "—")
        )

        lines = [f"*Оценка: {score}/10*\n"]
        if breakdown:
            lines.append("По критериям:")
            label_map = {
                "style": "Стиль",
                "structure": "Структура",
                "hook": "Зацепка",
                "content": "Фактура",
                "length": "Длина",
            }
            for k, v in breakdown.items():
                name = label_map.get(k, k)
                lines.append(f"  • {name}: {v}/10")
        if issues:
            lines.append("\nПроблемы:")
            for issue in issues:
                lines.append(f"  → {issue}")
        lines.append(f"\n*Решение: {decision}*")
        if result.get("comment"):
            lines.append(f"\n{result['comment']}")
        return "\n".join(lines)
