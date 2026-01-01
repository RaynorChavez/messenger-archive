#!/usr/bin/env python3
"""Insert missing chat messages from Jan 1, 2026."""

import sys
sys.path.insert(0, '/app')

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.db import SessionLocal, Message, Room, RoomMember

# Person IDs
RAYNOR = 31
WATSON = 3
BERNARD = 19
LENZ = 74
YOSH = 5

# Room ID
ROOM_ID = 1

# Messages to insert (timestamp, sender_id, content, reply_to_content)
# Base time: Jan 1, 2026 5:35 PM PHT (UTC+8)
messages = [
    # 5:35 PM
    ("2026-01-01T17:35:00+08:00", RAYNOR, "https://www.aifuturesmodel.com", None),
    
    # 5:50 PM
    ("2026-01-01T17:50:00+08:00", RAYNOR, "Prompt for the New Year: I think we need philosophers to think about what life will be like when AGI and ASI comes", None),
    ("2026-01-01T17:50:30+08:00", RAYNOR, "How will the people in the country adapt? How will life change? What will we all do? Old models of economic growth will be outdated. Everything will be outdated.", None),
    ("2026-01-01T17:52:00+08:00", WATSON, "Be skeptical about the hype, 10 years ago they said we'd have AGI in 10 years.", None),
    ("2026-01-01T17:52:30+08:00", WATSON, "Ah wait prompt pla I thought it was an actual prediction, my bad", None),
    ("2026-01-01T17:54:00+08:00", RAYNOR, "Id say im well placed to know the latest progress in AI, working at an AI company. It's all scary and exciting.", None),
    ("2026-01-01T17:55:00+08:00", RAYNOR, "The repercussions of labor being fully substitutable by capital are going to be huge.", None),
    ("2026-01-01T17:56:00+08:00", RAYNOR, "How will people live when all tasks can be done by AI and robots? Where will we get our meaning? Where will we get our wages? What will it mean to get the option for immortality? What will it mean to augment yourself with technology?", None),
    ("2026-01-01T17:57:00+08:00", BERNARD, "Marx predicted this lowk", None),
    ("2026-01-01T17:58:00+08:00", WATSON, "Similar to AI, I think it's gonna stay in fields like robotics, data science, and unfortunately in fields like military and surveillance, but\n\nI really doubt that service-based labor, or art, or intimacy-related stuff like sex or romance, will be changed much", None),
    ("2026-01-01T17:59:00+08:00", RAYNOR, "That covers most of the productive economy tho", None),
    ("2026-01-01T18:00:00+08:00", WATSON, "Right now, AI is very, very good at finding patterns\n\nFor better or for worse, life is much more than the technical tasks that AI is designed to do", None),
    ("2026-01-01T18:01:00+08:00", RAYNOR, "White collar and blue collar jobs", None),
    ("2026-01-01T18:01:30+08:00", WATSON, "Please be more specific", None),
    ("2026-01-01T18:02:00+08:00", WATSON, "These are big industries, but I think the term \"productive economy\" needs to be substantiated", None),
    ("2026-01-01T18:03:00+08:00", RAYNOR, "From secretaries, to engineers, coders, teachers, factory workers… every job that actually produces stuff", None),
    ("2026-01-01T18:03:30+08:00", RAYNOR, "Literally anything you can do on a computer", None),
    ("2026-01-01T18:04:00+08:00", RAYNOR, "Everything you can do with your body", None),
    ("2026-01-01T18:05:00+08:00", WATSON, "If they can do it better and/or cheaper, then I'd agree, but again, I'll believe it when I see it", None),
    ("2026-01-01T18:05:30+08:00", WATSON, "Tho embodied stuff isn't just AI now, that's robotics, and is an entirely separate field", None),
    ("2026-01-01T18:06:00+08:00", RAYNOR, "When you see it? By then itll be too late", None),
    ("2026-01-01T18:07:00+08:00", WATSON, "Maybe I've spent too much time digging into the history, but I am very, very skeptical\n\nIt all seems like hype trying to justify ever bigger investments", None),
    ("2026-01-01T18:08:00+08:00", RAYNOR, "We need to plan now", None),
    ("2026-01-01T18:08:30+08:00", WATSON, "That's true, AI safety is extremely important", None),
    ("2026-01-01T18:09:00+08:00", WATSON, "On this note tho, Robert Myles has great stuff on AI safety", None),
    ("2026-01-01T18:10:00+08:00", WATSON, "\"getting\" to AGI will involve a lot of very specific assumptions about intelligence and ability, such as the assumption that a different kind of mind can effectively adapt to the material world we live in", None),
    ("2026-01-01T18:11:00+08:00", RAYNOR, "If it happens, well be glad we prepared and made a way for humanity to thrive. If it doesnt, all we gain is self satisfaction on being correct. Therefore I say we need to act as if it will.\n\nAnd, all empirical evidence and indeed history points toward ever increasing capabilities in ai", None),
    ("2026-01-01T18:12:00+08:00", LENZ, "I would say just because someone did this https://www.agidefinition.ai (created metrics for what is AGI or not) then I'm more likely to believe AGI is a much more concrete goal if someone wants to build it", None),
    ("2026-01-01T18:13:00+08:00", LENZ, "I don't think it's easy but it's a better roadmap than 10 or 5 years ago", None),
    ("2026-01-01T18:14:00+08:00", WATSON, "Okok I agree with the first paragraph, tho the second paragraph is suspect because that's one hell of a blanket statement", None),
    ("2026-01-01T18:15:00+08:00", WATSON, "I subscribe to the Michael Reeves school of AI\n\nhttps://youtube.com/shorts/WP5_XJY_P0Q?si=8ND2P5sISW-IQ-RU", None),
    ("2026-01-01T18:16:00+08:00", WATSON, "chatgpt has E-stroke", None),
    
    # 6:46 PM
    ("2026-01-01T18:46:00+08:00", YOSH, "True, but never saying never doesn't mean \"it will\" either", None),
    ("2026-01-01T18:47:00+08:00", YOSH, "This goes for all future forecasts, not that forecasts are useless, but things in life never go the way you want it to", None),
    ("2026-01-01T18:48:00+08:00", YOSH, "You can plan all you want but there will be multiple paradigm shifts that we can't even comprehend as happening which will change the way we are even framing this argument", None),
    ("2026-01-01T18:49:00+08:00", YOSH, "A writer has an original vision for his work, but as he writes it, he discovers & creates himself & it", None),
    ("2026-01-01T18:50:00+08:00", YOSH, "Anxiety for AGI & ASI is humanistic - it's trapped in the past, I don't think most people who are running this operation actually see where they are", None),
    ("2026-01-01T18:51:00+08:00", RAYNOR, "What action do you think would be appropriate @Yosh?", None),
    ("2026-01-01T18:52:00+08:00", YOSH, "Personally I'm a maieutic figure, I don't care what people decide, I mostly care if they are asking the right questions", None),
    ("2026-01-01T18:53:00+08:00", YOSH, "To me, the vast majority of the people running this stuff have what I would call \"completely outdated / anthropocentric frameworks that have long since been transcended in the 20th century\"", None),
    ("2026-01-01T18:54:00+08:00", RAYNOR, "Would you advocate for a non-anthropocentric view?", None),
    ("2026-01-01T18:54:30+08:00", RAYNOR, "what would that look like?", None),
    ("2026-01-01T18:55:00+08:00", RAYNOR, "what remains invariant? what remains valuable and what remains scarce? New economics that need to be invented? new governments? etc", None),
    ("2026-01-01T18:55:30+08:00", RAYNOR, "we cant just sweep these things under the rug of \"different ontologies\"", None),
    ("2026-01-01T18:56:00+08:00", YOSH, "I don't think it \"needs\" to happen, that's an aesthetic (ethical) preference...", None),
    ("2026-01-01T18:57:00+08:00", YOSH, "Most people in AGI / ASI \"want\" it to happen because they live in one universe, where this will be a threat in the future. But that universe is their own anxieties", None),
    ("2026-01-01T18:58:00+08:00", YOSH, "I doubt the Industrial Revolution would've gone any differently had anyone planned for it, we all still would've been electrified & our relations to objects would be more or less similar to what it is now", None),
    ("2026-01-01T18:59:00+08:00", YOSH, "But you obviously feel differently. I'm just posing a question to all that through my own existence", None),
    ("2026-01-01T19:00:00+08:00", YOSH, "The mountains preach Dharma, so will computers-becoming-AGI & ASI", None),
    ("2026-01-01T19:01:00+08:00", RAYNOR, "that seems to be a fundamental reliquishment of any individual agency though", None),
    ("2026-01-01T19:01:30+08:00", RAYNOR, "how do you reconcile existence with that philosophy", None),
    ("2026-01-01T19:02:00+08:00", RAYNOR, "all of history is simply made by individuals", None),
    ("2026-01-01T19:03:00+08:00", RAYNOR, "I appreciate the perspective, though I don't think that this is a case of different yet equal ontologies. The need for discussion is based on strong empirical, historical, technological, economic, and sociological priors that are real and are pointing to observable trends. We ignore them to our peril.\n\nIf we see a massive technological paradigm shift coming that could disenfranchise billions, it feels irresponsible to just say \"reality is an aesthetic preference.\"", None),
]

def main():
    db = SessionLocal()
    try:
        # Get room's matrix_room_id for generating event IDs
        room = db.query(Room).filter(Room.id == ROOM_ID).first()
        if not room:
            print(f"Room {ROOM_ID} not found!")
            return
        
        inserted = 0
        skipped = 0
        
        for ts_str, sender_id, content, _ in messages:
            ts = datetime.fromisoformat(ts_str)
            
            # Check if message already exists (by content + sender + approximate time)
            existing = db.query(Message).filter(
                Message.sender_id == sender_id,
                Message.content == content,
                Message.room_id == ROOM_ID
            ).first()
            
            if existing:
                skipped += 1
                continue
            
            # Generate a unique event ID
            event_id = f"$manual_{ts.timestamp()}_{sender_id}_{inserted}"
            
            msg = Message(
                matrix_event_id=event_id,
                room_id=ROOM_ID,
                sender_id=sender_id,
                content=content,
                timestamp=ts
            )
            db.add(msg)
            inserted += 1
        
        db.commit()
        print(f"Inserted {inserted} messages, skipped {skipped} duplicates")
        
        # Update room member stats manually
        print("Updating room member stats...")
        sender_ids = set(m[1] for m in messages)
        for sender_id in sender_ids:
            stats = db.query(
                func.count(Message.id),
                func.min(Message.timestamp),
                func.max(Message.timestamp)
            ).filter(
                Message.room_id == ROOM_ID,
                Message.sender_id == sender_id
            ).first()
            
            member = db.query(RoomMember).filter(
                RoomMember.room_id == ROOM_ID,
                RoomMember.person_id == sender_id
            ).first()
            
            if member:
                member.message_count = stats[0] or 0
                member.first_seen_at = stats[1]
                member.last_seen_at = stats[2]
            else:
                member = RoomMember(
                    room_id=ROOM_ID,
                    person_id=sender_id,
                    message_count=stats[0] or 0,
                    first_seen_at=stats[1],
                    last_seen_at=stats[2]
                )
                db.add(member)
        
        # Update room message count
        room.message_count = db.query(func.count(Message.id)).filter(Message.room_id == ROOM_ID).scalar()
        room.last_message_at = db.query(func.max(Message.timestamp)).filter(Message.room_id == ROOM_ID).scalar()
        
        db.commit()
        print("Done!")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
