"""Steam 이 game 으로 준 소프트웨어를 장르로 가려낸다."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store


def g(genres):
    return {"genres": genres}


class SoftwareTest(unittest.TestCase):
    def test_software_only(self):
        self.assertTrue(store.is_software(g("유틸리티")))
        self.assertTrue(store.is_software(g("오디오 제작, 유틸리티, 앞서 해보기")))
        self.assertTrue(store.is_software(g("인디, 유틸리티")))               # 인디·캐주얼은 게임 근거가 아니다

    def test_many_software_genres_beat_play_genre(self):
        self.assertTrue(store.is_software(g("시뮬레이션, 유틸리티, 동영상 제작, 웹 퍼블리싱")))

    def test_games_kept(self):
        self.assertFalse(store.is_software(g("액션, 어드벤처, 인디")))
        self.assertFalse(store.is_software(g("RPG, 무료 플레이, 유틸리티")))
        self.assertFalse(store.is_software(g("액션, 어드벤처, 캐주얼, 인디, 스포츠, 교육")))  # 교육 게임
        self.assertFalse(store.is_software(g("")))


if __name__ == "__main__":
    unittest.main()
