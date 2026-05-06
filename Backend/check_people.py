#!/usr/bin/env python3
"""
Quick check of people registered for Moustafa Osman
"""

import asyncio
from app.database import connect_to_mongo, get_db

async def check_people():
    await connect_to_mongo()
    db = get_db()
    people = []
    async for person in db.people.find({'user_id': '69c5cfd79a8741407bef64fa'}):
        people.append({
            'name': person.get('name'),
            'has_face': 'Yes' if person.get('face_embedding') else 'No',
            'has_voice': 'Yes' if person.get('voice_embedding') else 'No',
            'relation': person.get('relation', 'N/A')
        })

    print('People registered for Moustafa Osman:')
    print('=' * 50)
    for p in people:
        print(f'  {p["name"]:15} | Face: {p["has_face"]} | Voice: {p["has_voice"]} | Relation: {p["relation"]}')

    print(f'\nTotal: {len(people)} people')

if __name__ == "__main__":
    asyncio.run(check_people())