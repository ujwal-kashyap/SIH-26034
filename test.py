class Solution:
    def groupAnagrams(self, strs: list[str]) -> list[list[str]]:
        letters = "abcdefghijklmnopqrstuvwxyz"
        dic = {}

        for i in strs:
            count = [0] * 26

            for x in i:
                index = letters.index(x)
                count[index] += 1

            key = tuple(count)

            if key not in dic:
                dic[key] = []

            dic[key].append(i)

        return list(dic.values())

print(Solution().groupAnagrams(["eat","tea","tan","ate","nat","bat"]))