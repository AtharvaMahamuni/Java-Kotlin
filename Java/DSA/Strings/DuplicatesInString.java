package DSA.Strings;

import java.util.HashSet;

public class DuplicatesInString {

    public static String duplicateString(String sentence) {

        HashSet<Character> diary = new HashSet<Character>();

        // int write = 0;
        String newSent = "";
        for (int read = 0; read < sentence.length(); read++) {

            if (!diary.contains(sentence.charAt(read))) {
                newSent = newSent + sentence.charAt(read);
                diary.add(sentence.charAt(read));
            }
        }

        return newSent;
    }

    public static void main(String[] args) {
        System.out.println(duplicateString("ABDBCDEFGAN"));
    }
}
