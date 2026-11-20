import unittest
from update_data import eligible, nm_stat, hhmmss, normalize

class DashboardTests(unittest.TestCase):
    def test_whitelist(self):
        for code in ['600519','601888','603001','605001','000001','001333','002594','003000']:
            self.assertTrue(eligible(code,'普通股票'))
        for code in ['300001','301333','688001','689009','920001','430001','832001','200001']:
            self.assertFalse(eligible(code,'普通股票'))
    def test_name_excludes(self):
        for name in ['ST测试','*ST风险','S*ST风险','退市整理','N新股','C新股']:
            self.assertFalse(eligible('600001',name))
    def test_nm(self):
        self.assertEqual(nm_stat('5/3',2),(5,3))
        self.assertEqual(nm_stat('6天4板',1),(6,4))
        self.assertEqual(nm_stat(None,3),(3,3))
        self.assertEqual(nm_stat('待核实',0),(None,None))
    def test_hhmmss(self):
        self.assertEqual(hhmmss(93500),'09:35')
        self.assertEqual(hhmmss('14:58:20'),'14:58')

if __name__=='__main__':unittest.main()
